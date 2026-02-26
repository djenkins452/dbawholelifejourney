# ==============================================================================
# File: apps/core/services/test_user_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Provisions a dedicated test user for automated UI testing
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-26
# ==============================================================================
"""
Test User Provisioning Service — single source of truth for creating and
maintaining the automated UI test user account.

Security:
    - ONLY modifies the specific test user (never touches other accounts)
    - Requires DEBUG=True or ALLOW_TEST_USER_CREATION=True
    - Does NOT disable verification/MFA globally — only for this user
    - Does NOT modify authentication logic or user model structure

Usage:
    from apps.core.services.test_user_service import ensure_test_user_exists
    user = ensure_test_user_exists("autotest@local.test", "testpass123")
"""

import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)

# Defaults when env vars are not set
DEFAULT_TEST_EMAIL = "autotest@local.test"
DEFAULT_TEST_PASSWORD = "testpass123"


def get_test_credentials():
    """Return (email, password) for the test user from env vars or defaults.

    Reads:
        WLJ_TEST_EMAIL — defaults to autotest@local.test
        WLJ_TEST_PASSWORD — defaults to testpass123
    """
    email = os.environ.get("WLJ_TEST_EMAIL", DEFAULT_TEST_EMAIL)
    password = os.environ.get("WLJ_TEST_PASSWORD", DEFAULT_TEST_PASSWORD)
    return email, password


def is_provisioning_allowed():
    """Check whether test user provisioning is allowed in this environment.

    Returns True if:
        - settings.DEBUG is True, OR
        - ALLOW_TEST_USER_CREATION env var is truthy
    """
    if getattr(settings, "DEBUG", False):
        return True
    allow_env = os.environ.get("ALLOW_TEST_USER_CREATION", "").lower()
    return allow_env in ("true", "1", "yes")


def ensure_test_user_exists(email=None, password=None):
    """Create or update the automated test user account.

    Idempotent — safe to call repeatedly. Creates the user if missing,
    updates fields if existing.

    Args:
        email: Test user email. Defaults to WLJ_TEST_EMAIL env var or
            autotest@local.test.
        password: Test user password. Defaults to WLJ_TEST_PASSWORD env var
            or testpass123.

    Returns:
        dict with keys: user, email, created, verified, mfa_disabled

    Raises:
        PermissionError: If provisioning is not allowed in this environment.
    """
    if not is_provisioning_allowed():
        raise PermissionError(
            "Test user provisioning not allowed. "
            "Set DEBUG=True or ALLOW_TEST_USER_CREATION=True."
        )

    if email is None or password is None:
        default_email, default_password = get_test_credentials()
        email = email or default_email
        password = password or default_password

    # Import models lazily to avoid circular imports at module level
    from apps.users.models import User, UserPreferences

    # 1. Create or get the user
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            "first_name": "UI",
            "last_name": "Tester",
            "is_active": True,
            "is_staff": True,
            "is_superuser": True,
            "is_app_review_account": True,
        },
    )

    if not created:
        # Ensure correct state on existing user
        user.first_name = "UI"
        user.last_name = "Tester"
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.is_app_review_account = True

    # Always set password (handles password changes)
    user.set_password(password)
    user.save()

    action = "Created" if created else "Updated"
    logger.info("Test user %s: %s", action.lower(), email)

    # 2. Verify email via allauth
    verified = _ensure_email_verified(user, email)

    # 3. Ensure preferences are set up (onboarding complete, modules enabled)
    _ensure_preferences(user)

    # 4. Disable MFA if any MFA-related fields exist (after prefs exist)
    mfa_disabled = _disable_mfa(user)

    return {
        "user": user,
        "email": email,
        "created": created,
        "verified": verified,
        "mfa_disabled": mfa_disabled,
    }


def _ensure_email_verified(user, email):
    """Mark the test user's email as verified in allauth.

    Returns True if verification was set/confirmed.
    """
    try:
        from allauth.account.models import EmailAddress

        email_obj, _ = EmailAddress.objects.update_or_create(
            user=user,
            email=email,
            defaults={
                "verified": True,
                "primary": True,
            },
        )
        logger.debug("Email verified for test user: %s", email)
        return True
    except ImportError:
        logger.warning("django-allauth not installed, skipping email verification")
        return False
    except Exception as exc:
        logger.error("Failed to verify email for test user: %s", exc)
        return False


def _disable_mfa(user):
    """Ensure MFA is disabled/bypassed for the test user.

    WLJ uses ``is_app_review_account = True`` on the User model to bypass
    MFA and security checks. This flag is set during user creation.

    Also checks for optional MFA fields (mfa_enabled, two_factor_enabled,
    otp_required) in case the model is extended in the future.

    Returns True if MFA bypass is confirmed active.
    """
    changed = False

    # Check future-proofing MFA fields on User model
    for field_name in ("mfa_enabled", "two_factor_enabled", "otp_required"):
        if hasattr(user, field_name):
            setattr(user, field_name, False)
            changed = True

    if changed:
        user.save()

    # The primary MFA bypass in WLJ is is_app_review_account
    mfa_bypassed = getattr(user, "is_app_review_account", False)

    if mfa_bypassed or changed:
        logger.debug("MFA disabled for test user: %s", user.email)

    return mfa_bypassed or changed


def _ensure_preferences(user):
    """Set up UserPreferences for the test user: onboarding complete, modules enabled."""
    try:
        from apps.users.models import UserPreferences

        prefs, _ = UserPreferences.objects.get_or_create(user=user)
        prefs.has_completed_onboarding = True
        prefs.health_enabled = True
        prefs.journal_enabled = True
        prefs.faith_enabled = True
        prefs.life_enabled = True
        prefs.purpose_enabled = True
        prefs.ai_enabled = True
        prefs.capture_enabled = True
        prefs.scan_enabled = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.email_notifications_enabled = False
        prefs.notifications_enabled = False
        prefs.save()
        logger.debug("Preferences configured for test user: %s", user.email)
    except Exception as exc:
        logger.warning("Failed to set preferences for test user: %s", exc)
