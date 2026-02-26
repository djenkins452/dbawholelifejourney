# ==============================================================================
# File: apps/core/tests/test_test_user_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for test user provisioning service
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-26
# ==============================================================================

from unittest.mock import patch

from django.test import TestCase, override_settings

from allauth.account.models import EmailAddress

from apps.core.services.test_user_service import (
    ensure_test_user_exists,
    get_test_credentials,
    is_provisioning_allowed,
)
from apps.users.models import User, UserPreferences


class TestIsProvisioningAllowed(TestCase):
    """Test the environment guard for test user provisioning."""

    @override_settings(DEBUG=True)
    def test_allowed_in_debug_mode(self):
        self.assertTrue(is_provisioning_allowed())

    @override_settings(DEBUG=False)
    @patch.dict("os.environ", {"ALLOW_TEST_USER_CREATION": ""})
    def test_blocked_in_production(self):
        self.assertFalse(is_provisioning_allowed())

    @override_settings(DEBUG=False)
    @patch.dict("os.environ", {"ALLOW_TEST_USER_CREATION": "true"})
    def test_allowed_with_env_var(self):
        self.assertTrue(is_provisioning_allowed())

    @override_settings(DEBUG=False)
    @patch.dict("os.environ", {"ALLOW_TEST_USER_CREATION": "1"})
    def test_allowed_with_env_var_numeric(self):
        self.assertTrue(is_provisioning_allowed())


class TestGetTestCredentials(TestCase):
    """Test credential retrieval from env vars."""

    @patch.dict("os.environ", {}, clear=True)
    def test_defaults_when_no_env_vars(self):
        # Clear specific vars if present
        import os
        os.environ.pop("WLJ_TEST_EMAIL", None)
        os.environ.pop("WLJ_TEST_PASSWORD", None)
        email, password = get_test_credentials()
        self.assertEqual(email, "autotest@local.test")
        self.assertEqual(password, "testpass123")

    @patch.dict("os.environ", {
        "WLJ_TEST_EMAIL": "custom@test.com",
        "WLJ_TEST_PASSWORD": "custompass",
    })
    def test_reads_env_vars(self):
        email, password = get_test_credentials()
        self.assertEqual(email, "custom@test.com")
        self.assertEqual(password, "custompass")


@override_settings(DEBUG=True)
class TestEnsureTestUserExists(TestCase):
    """Test the core provisioning function."""

    def test_creates_user(self):
        """Command creates a new test user."""
        result = ensure_test_user_exists("uitest@test.com", "testpass")

        self.assertTrue(result["created"])
        self.assertEqual(result["email"], "uitest@test.com")

        user = User.objects.get(email="uitest@test.com")
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_app_review_account)
        self.assertTrue(user.check_password("testpass"))

    def test_verifies_email(self):
        """Command marks email as verified via allauth."""
        result = ensure_test_user_exists("uitest@test.com", "testpass")
        self.assertTrue(result["verified"])

        email_addr = EmailAddress.objects.get(
            user__email="uitest@test.com",
            email="uitest@test.com",
        )
        self.assertTrue(email_addr.verified)
        self.assertTrue(email_addr.primary)

    def test_disables_mfa(self):
        """Command disables MFA via is_app_review_account flag."""
        result = ensure_test_user_exists("uitest@test.com", "testpass")
        self.assertTrue(result["mfa_disabled"])

        user = User.objects.get(email="uitest@test.com")
        self.assertTrue(user.is_app_review_account)

    def test_idempotent(self):
        """Running twice does not create duplicates."""
        result1 = ensure_test_user_exists("uitest@test.com", "testpass")
        result2 = ensure_test_user_exists("uitest@test.com", "testpass")

        self.assertTrue(result1["created"])
        self.assertFalse(result2["created"])
        self.assertEqual(User.objects.filter(email="uitest@test.com").count(), 1)

    def test_updates_password_on_rerun(self):
        """Running with a new password updates the existing user."""
        ensure_test_user_exists("uitest@test.com", "oldpass")
        ensure_test_user_exists("uitest@test.com", "newpass")

        user = User.objects.get(email="uitest@test.com")
        self.assertTrue(user.check_password("newpass"))
        self.assertFalse(user.check_password("oldpass"))

    @override_settings(DEBUG=False)
    @patch.dict("os.environ", {"ALLOW_TEST_USER_CREATION": ""})
    def test_respects_environment_guard(self):
        """Provisioning raises PermissionError when not allowed."""
        with self.assertRaises(PermissionError):
            ensure_test_user_exists("uitest@test.com", "testpass")

    def test_sets_up_preferences(self):
        """Command configures preferences with onboarding complete and modules enabled."""
        ensure_test_user_exists("uitest@test.com", "testpass")

        prefs = UserPreferences.objects.get(user__email="uitest@test.com")
        self.assertTrue(prefs.has_completed_onboarding)
        self.assertTrue(prefs.health_enabled)
        self.assertTrue(prefs.journal_enabled)
        self.assertTrue(prefs.faith_enabled)
        self.assertTrue(prefs.life_enabled)
        self.assertTrue(prefs.purpose_enabled)


class TestCreateTestUserCommand(TestCase):
    """Test the management command wrapper."""

    @override_settings(DEBUG=True)
    def test_command_runs_successfully(self):
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("create_test_user", stdout=out)

        output = out.getvalue()
        self.assertIn("Test user ready", output)
        self.assertIn("autotest@local.test", output)
        self.assertIn("verified: True", output)

    @override_settings(DEBUG=False)
    @patch.dict("os.environ", {"ALLOW_TEST_USER_CREATION": ""})
    def test_command_aborts_in_production(self):
        from django.core.management import call_command
        from io import StringIO

        err = StringIO()
        call_command("create_test_user", stderr=err)

        output = err.getvalue()
        self.assertIn("ABORTED", output)

        # No user created
        self.assertFalse(User.objects.filter(email="autotest@local.test").exists())
