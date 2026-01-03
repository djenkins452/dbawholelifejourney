# ==============================================================================
# File: test_signup_security.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for signup security features including email verification
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================

"""
Signup Security Tests

Tests for:
1. Email verification flow
2. Unverified user restrictions
3. Verification link activation
4. Post-verification flow to terms acceptance
"""

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core import mail
from allauth.account.models import EmailAddress, EmailConfirmationHMAC

User = get_user_model()


class EmailVerificationFlowTest(TestCase):
    """Tests for the email verification flow."""

    def setUp(self):
        self.client = Client()
        self.signup_url = reverse('account_signup')
        self.login_url = reverse('account_login')

    def test_signup_requires_email_verification(self):
        """New signup should create user that requires email verification."""
        # Sign up a new user
        response = self.client.post(self.signup_url, {
            'email': 'newuser@example.com',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        })

        # User should be created
        self.assertTrue(User.objects.filter(email='newuser@example.com').exists())
        user = User.objects.get(email='newuser@example.com')

        # Email address should exist but not be verified
        email_address = EmailAddress.objects.get(user=user, email='newuser@example.com')
        self.assertFalse(email_address.verified)

        # Verification email should have been sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Verify your Whole Life Journey account', mail.outbox[0].subject)

    def test_unverified_user_redirected_to_verification_page(self):
        """Unverified user attempting to access protected pages should be redirected."""
        # Create user without verified email
        user = User.objects.create_user(
            email='unverified@example.com',
            password='testpass123'
        )
        EmailAddress.objects.create(
            user=user,
            email='unverified@example.com',
            verified=False,
            primary=True
        )

        # Login attempt should redirect to verification pending
        self.client.login(email='unverified@example.com', password='testpass123')
        response = self.client.get(reverse('dashboard:home'))

        # Should redirect (302) - unverified users can't access dashboard
        self.assertEqual(response.status_code, 302)

    def test_verification_link_activates_user(self):
        """Clicking verification link should verify the email address."""
        # Create user with unverified email
        user = User.objects.create_user(
            email='toactivate@example.com',
            password='testpass123'
        )
        email_address = EmailAddress.objects.create(
            user=user,
            email='toactivate@example.com',
            verified=False,
            primary=True
        )

        # Generate confirmation key
        confirmation = EmailConfirmationHMAC(email_address)
        key = confirmation.key

        # Visit confirmation URL
        confirm_url = reverse('account_confirm_email', args=[key])
        response = self.client.post(confirm_url)

        # Email should now be verified
        email_address.refresh_from_db()
        self.assertTrue(email_address.verified)

    def test_verified_user_proceeds_to_terms_acceptance(self):
        """Verified user without terms accepted should be redirected to terms page."""
        # Create user with verified email but no terms accepted
        user = User.objects.create_user(
            email='verified@example.com',
            password='testpass123'
        )
        EmailAddress.objects.create(
            user=user,
            email='verified@example.com',
            verified=True,
            primary=True
        )

        # Login
        self.client.login(email='verified@example.com', password='testpass123')

        # Access dashboard - should redirect to terms (user hasn't accepted yet)
        response = self.client.get(reverse('dashboard:home'))

        # Should redirect to terms acceptance
        self.assertEqual(response.status_code, 302)
        # The redirect should be to terms or onboarding flow
        self.assertIn('terms', response.url.lower())

    def test_signup_sends_branded_email(self):
        """Verification email should use branded template."""
        response = self.client.post(self.signup_url, {
            'email': 'brandtest@example.com',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        })

        # Check email was sent with branding
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        # Subject may include site prefix like "[example.com]"
        self.assertIn('Verify your Whole Life Journey account', email.subject)
        self.assertIn('Whole Life Journey', email.body)
        self.assertIn('verify', email.body.lower())


class EmailVerificationEdgeCasesTest(TestCase):
    """Edge case tests for email verification."""

    def setUp(self):
        self.client = Client()

    def test_double_verification_does_not_unverify(self):
        """Verifying an already verified email should keep it verified."""
        # Create user with unverified email
        user = User.objects.create_user(
            email='doublecheck@example.com',
            password='testpass123'
        )
        email_address = EmailAddress.objects.create(
            user=user,
            email='doublecheck@example.com',
            verified=False,
            primary=True
        )

        # Generate confirmation key and verify
        confirmation = EmailConfirmationHMAC(email_address)
        key = confirmation.key
        confirm_url = reverse('account_confirm_email', args=[key])

        # First verification via POST
        self.client.post(confirm_url)
        email_address.refresh_from_db()
        self.assertTrue(email_address.verified)

        # Second verification attempt should not unverify
        self.client.post(confirm_url)
        email_address.refresh_from_db()
        self.assertTrue(email_address.verified)
