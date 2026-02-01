# ==============================================================================
# File: test_admin_email.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to test email delivery to admin for the
#              Personal Assistant feature
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-05
# ==============================================================================

"""
Test Admin Email Management Command

Sends a test email to admin@wholelifejourney.com to verify the email backend
is correctly configured for the WLJ Personal Assistant.

Usage:
    python manage.py test_admin_email
    python manage.py test_admin_email --dry-run
    python manage.py test_admin_email --recipient custom@example.com
"""

import socket

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Send a test email to verify Personal Assistant email configuration"

    def add_arguments(self, parser):
        parser.add_argument(
            "--recipient",
            type=str,
            default="admin@wholelifejourney.com",
            help="Email address to send the test email to (default: admin@wholelifejourney.com)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show configuration without sending email",
        )

    def handle(self, *args, **options):
        recipient = options["recipient"]
        dry_run = options["dry_run"]

        # Get server information
        try:
            server_name = socket.gethostname()
        except Exception:
            server_name = "Unknown"

        # Display current configuration
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("WLJ PERSONAL ASSISTANT - EMAIL CONFIGURATION TEST")
        self.stdout.write("=" * 60)

        backend = getattr(settings, "EMAIL_BACKEND", "Not set")
        self.stdout.write(f"Backend:      {backend}")

        is_smtp = "smtp" in backend.lower()

        if is_smtp:
            host = getattr(settings, "EMAIL_HOST", "Not set")
            port = getattr(settings, "EMAIL_PORT", "Not set")
            use_tls = getattr(settings, "EMAIL_USE_TLS", False)
            use_ssl = getattr(settings, "EMAIL_USE_SSL", False)
            user = getattr(settings, "EMAIL_HOST_USER", "Not set")
            password_set = bool(getattr(settings, "EMAIL_HOST_PASSWORD", ""))
            timeout = getattr(settings, "EMAIL_TIMEOUT", "Not set")

            self.stdout.write(f"Host:         {host}")
            self.stdout.write(f"Port:         {port}")
            self.stdout.write(f"TLS:          {use_tls}")
            self.stdout.write(f"SSL:          {use_ssl}")
            self.stdout.write(f"Username:     {user}")
            self.stdout.write(f"Password:     {'***SET***' if password_set else 'NOT SET'}")
            self.stdout.write(f"Timeout:      {timeout}s")

        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "Not set")
        self.stdout.write(f"From Address: {from_email}")
        self.stdout.write(f"Recipient:    {recipient}")
        self.stdout.write(f"Server Name:  {server_name}")
        self.stdout.write(f"Debug Mode:   {settings.DEBUG}")
        self.stdout.write("=" * 60 + "\n")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN - No email sent")
            )
            return

        # Warn about console backend
        if "console" in backend.lower():
            self.stdout.write(
                self.style.WARNING(
                    "\nNote: Console backend is active (DEBUG mode). "
                    "Email will print to stdout, not sent via SMTP.\n"
                    "To test actual email delivery, run this on production or "
                    "set DEBUG=False with SMTP credentials.\n"
                )
            )

        # Compose email
        timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S %Z")
        subject = "WLJ Personal Assistant - Email Test"
        message = f"""WLJ Personal Assistant - Email Test
=====================================

This is a test email from the Whole Life Journey Personal Assistant.

Timestamp: {timestamp}
Server: {server_name}
Environment: {'Development' if settings.DEBUG else 'Production'}

If you received this email, the email backend is configured correctly
and the Personal Assistant can send notifications.

---
Email Configuration Details:
  Backend: {backend}
  From: {from_email}
  SMTP Host: {getattr(settings, 'EMAIL_HOST', 'N/A')}
  SMTP Port: {getattr(settings, 'EMAIL_PORT', 'N/A')}
  TLS: {getattr(settings, 'EMAIL_USE_TLS', 'N/A')}

---
To re-run this test:
  python manage.py test_admin_email

To test with a different recipient:
  python manage.py test_admin_email --recipient your@email.com
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
                    self.style.SUCCESS(
                        f"\n SUCCESS: Test email sent to {recipient}"
                    )
                )
                if "console" not in backend.lower():
                    self.stdout.write(
                        self.style.SUCCESS(
                            "Check your inbox (and spam folder) to confirm delivery."
                        )
                    )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"\n WARNING: send_mail returned {result} - email may not have been sent"
                    )
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR("\n FAILED: Could not send email")
            )
            self.stdout.write(f"Error: {e}")
            self.stdout.write("\nTroubleshooting tips:")
            self.stdout.write("  1. Verify EMAIL_HOST_USER and EMAIL_HOST_PASSWORD are set in environment")
            self.stdout.write("  2. Confirm SMTP credentials are correct (check Namecheap Private Email)")
            self.stdout.write("  3. Check if port 587 is blocked (try 465 with SSL if needed)")
            self.stdout.write("  4. Ensure DEFAULT_FROM_EMAIL matches EMAIL_HOST_USER for SPF/DKIM")
            raise CommandError(f"Email send failed: {e}")
