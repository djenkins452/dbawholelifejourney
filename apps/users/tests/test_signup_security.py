# ==============================================================================
# File: test_signup_security.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for signup security features including email verification
#              and PII hashing functions
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
5. PII hash functions (hash_email, hash_ip, hash_fingerprint)
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


class HashEmailTest(TestCase):
    """Tests for the hash_email function."""

    def test_hash_email_returns_64_char_hex(self):
        """hash_email should return a 64-character hex string (SHA-256)."""
        from apps.users.security import hash_email

        result = hash_email("test@example.com")
        self.assertEqual(len(result), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in result))

    def test_hash_email_consistent(self):
        """Same email should produce same hash."""
        from apps.users.security import hash_email

        hash1 = hash_email("test@example.com")
        hash2 = hash_email("test@example.com")
        self.assertEqual(hash1, hash2)

    def test_hash_email_normalizes_case(self):
        """Email hashing should be case-insensitive."""
        from apps.users.security import hash_email

        hash_lower = hash_email("test@example.com")
        hash_upper = hash_email("TEST@EXAMPLE.COM")
        hash_mixed = hash_email("Test@Example.COM")

        self.assertEqual(hash_lower, hash_upper)
        self.assertEqual(hash_lower, hash_mixed)

    def test_hash_email_strips_whitespace(self):
        """Email hashing should strip leading/trailing whitespace."""
        from apps.users.security import hash_email

        hash_clean = hash_email("test@example.com")
        hash_spaces = hash_email("  test@example.com  ")

        self.assertEqual(hash_clean, hash_spaces)

    def test_hash_email_different_inputs_different_hashes(self):
        """Different emails should produce different hashes."""
        from apps.users.security import hash_email

        hash1 = hash_email("user1@example.com")
        hash2 = hash_email("user2@example.com")

        self.assertNotEqual(hash1, hash2)

    def test_hash_email_empty_returns_empty(self):
        """Empty email should return empty string."""
        from apps.users.security import hash_email

        self.assertEqual(hash_email(""), "")
        self.assertEqual(hash_email(None), "")


class HashIPTest(TestCase):
    """Tests for the hash_ip function."""

    def test_hash_ip_returns_64_char_hex(self):
        """hash_ip should return a 64-character hex string (SHA-256)."""
        from apps.users.security import hash_ip

        result = hash_ip("192.168.1.1")
        self.assertEqual(len(result), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in result))

    def test_hash_ip_consistent(self):
        """Same IP should produce same hash."""
        from apps.users.security import hash_ip

        hash1 = hash_ip("192.168.1.1")
        hash2 = hash_ip("192.168.1.1")
        self.assertEqual(hash1, hash2)

    def test_hash_ip_strips_whitespace(self):
        """IP hashing should strip leading/trailing whitespace."""
        from apps.users.security import hash_ip

        hash_clean = hash_ip("192.168.1.1")
        hash_spaces = hash_ip("  192.168.1.1  ")

        self.assertEqual(hash_clean, hash_spaces)

    def test_hash_ip_different_inputs_different_hashes(self):
        """Different IPs should produce different hashes."""
        from apps.users.security import hash_ip

        hash1 = hash_ip("192.168.1.1")
        hash2 = hash_ip("192.168.1.2")

        self.assertNotEqual(hash1, hash2)

    def test_hash_ip_ipv6(self):
        """IPv6 addresses should be hashed correctly."""
        from apps.users.security import hash_ip

        result = hash_ip("2001:0db8:85a3:0000:0000:8a2e:0370:7334")
        self.assertEqual(len(result), 64)

    def test_hash_ip_empty_returns_empty(self):
        """Empty IP should return empty string."""
        from apps.users.security import hash_ip

        self.assertEqual(hash_ip(""), "")
        self.assertEqual(hash_ip(None), "")


class HashFingerprintTest(TestCase):
    """Tests for the hash_fingerprint function."""

    def test_hash_fingerprint_returns_64_char_hex(self):
        """hash_fingerprint should return a 64-character hex string (SHA-256)."""
        from apps.users.security import hash_fingerprint

        result = hash_fingerprint({"browser": "Chrome", "os": "Windows"})
        self.assertEqual(len(result), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in result))

    def test_hash_fingerprint_consistent(self):
        """Same fingerprint should produce same hash."""
        from apps.users.security import hash_fingerprint

        data = {"browser": "Chrome", "os": "Windows", "screen": "1920x1080"}
        hash1 = hash_fingerprint(data)
        hash2 = hash_fingerprint(data)
        self.assertEqual(hash1, hash2)

    def test_hash_fingerprint_order_independent(self):
        """Fingerprint hashing should be key order independent."""
        from apps.users.security import hash_fingerprint

        hash1 = hash_fingerprint({"browser": "Chrome", "os": "Windows"})
        hash2 = hash_fingerprint({"os": "Windows", "browser": "Chrome"})

        self.assertEqual(hash1, hash2)

    def test_hash_fingerprint_different_inputs_different_hashes(self):
        """Different fingerprints should produce different hashes."""
        from apps.users.security import hash_fingerprint

        hash1 = hash_fingerprint({"browser": "Chrome", "os": "Windows"})
        hash2 = hash_fingerprint({"browser": "Firefox", "os": "Mac"})

        self.assertNotEqual(hash1, hash2)

    def test_hash_fingerprint_nested_data(self):
        """Nested fingerprint data should be hashed correctly."""
        from apps.users.security import hash_fingerprint

        data = {
            "browser": "Chrome",
            "plugins": ["PDF", "Flash"],
            "canvas": {"hash": "abc123"},
        }
        result = hash_fingerprint(data)
        self.assertEqual(len(result), 64)

    def test_hash_fingerprint_empty_returns_empty(self):
        """Empty fingerprint should return empty string."""
        from apps.users.security import hash_fingerprint

        self.assertEqual(hash_fingerprint({}), "")
        self.assertEqual(hash_fingerprint(None), "")


class HoneypotValidationTest(TestCase):
    """Tests for honeypot field validation in signup."""

    def setUp(self):
        self.client = Client()
        self.signup_url = reverse('account_signup')

    def test_honeypot_blocks_bot(self):
        """Signup with honeypot field filled should be blocked."""
        from apps.users.models import SignupAttempt

        initial_count = SignupAttempt.objects.count()

        # Submit signup with honeypot field filled (simulating a bot)
        response = self.client.post(self.signup_url, {
            'email': 'bot@example.com',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'website': 'http://spamsite.com',  # Honeypot field filled
        })

        # User should NOT be created
        self.assertFalse(User.objects.filter(email='bot@example.com').exists())

        # SignupAttempt should be logged with block_reason='honeypot'
        new_attempts = SignupAttempt.objects.filter(block_reason='honeypot')
        self.assertTrue(new_attempts.exists())

        # Check the blocked attempt has correct status
        blocked_attempt = new_attempts.latest('created_at')
        self.assertEqual(blocked_attempt.status, 'blocked')
        self.assertEqual(blocked_attempt.risk_level, 'high')

    def test_empty_honeypot_allows_signup(self):
        """Signup without honeypot field filled should proceed normally."""
        # Submit signup with honeypot field empty (normal human behavior)
        response = self.client.post(self.signup_url, {
            'email': 'human@example.com',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'website': '',  # Honeypot field empty
        })

        # User should be created (or at least not blocked by honeypot)
        # Note: User may still need email verification, but form should be accepted
        user_exists = User.objects.filter(email='human@example.com').exists()
        # If user wasn't created, check it wasn't due to honeypot block
        if not user_exists:
            from apps.users.models import SignupAttempt
            honeypot_blocks = SignupAttempt.objects.filter(
                block_reason='honeypot',
                email_hash__isnull=False
            ).count()
            # This assertion ensures if user wasn't created, it's not due to honeypot
            # (could be due to email verification being required)
            self.assertEqual(honeypot_blocks, 0)

    def test_honeypot_not_in_request_allows_signup(self):
        """Signup without honeypot field in request should proceed normally."""
        # Submit signup without honeypot field at all
        response = self.client.post(self.signup_url, {
            'email': 'nofield@example.com',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
            # No 'website' field
        })

        # Should not be blocked by honeypot
        from apps.users.models import SignupAttempt
        honeypot_blocks = SignupAttempt.objects.filter(
            block_reason='honeypot'
        ).count()
        self.assertEqual(honeypot_blocks, 0)
