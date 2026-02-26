# ==============================================================================
# File: apps/core/management/commands/create_test_user.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to provision the automated UI test user
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-26
# ==============================================================================
"""
Create or update the automated UI test user for Playwright-based testing.

Usage:
    python manage.py create_test_user

Environment variables:
    WLJ_TEST_EMAIL     — Test user email (default: autotest@local.test)
    WLJ_TEST_PASSWORD  — Test user password (default: testpass123)

Safety:
    Only runs when DEBUG=True or ALLOW_TEST_USER_CREATION=True.
    Aborts with clear error otherwise.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update the automated UI test user account"

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            default=None,
            help="Override test user email (default: WLJ_TEST_EMAIL env var or autotest@local.test)",
        )
        parser.add_argument(
            "--password",
            type=str,
            default=None,
            help="Override test user password (default: WLJ_TEST_PASSWORD env var or testpass123)",
        )

    def handle(self, *args, **options):
        from apps.core.services.test_user_service import (
            ensure_test_user_exists,
            is_provisioning_allowed,
            get_test_credentials,
        )

        # Check environment guard
        if not is_provisioning_allowed():
            self.stderr.write(
                self.style.ERROR(
                    "ABORTED: Test user provisioning not allowed.\n"
                    "Set DEBUG=True or ALLOW_TEST_USER_CREATION=True to enable."
                )
            )
            return

        email = options.get("email")
        password = options.get("password")

        # Show what credentials will be used
        if not email or not password:
            default_email, default_password = get_test_credentials()
            email = email or default_email
            password = password or default_password

        try:
            result = ensure_test_user_exists(email=email, password=password)
        except PermissionError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Failed to create test user: {exc}"))
            return

        # Output summary
        action = "Created" if result["created"] else "Updated"
        self.stdout.write(self.style.SUCCESS(f"\nTest user ready ({action.lower()}):"))
        self.stdout.write(f"  email:    {result['email']}")
        self.stdout.write(f"  verified: {result['verified']}")
        self.stdout.write(f"  mfa:      {'disabled' if result['mfa_disabled'] else 'n/a'}")
        self.stdout.write("")
