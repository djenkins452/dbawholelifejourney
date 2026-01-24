"""
MFA Email Code Tests

Tests for:
1. MFAEmailCode model
2. Email code send endpoint
3. Email code verify endpoint
4. MFA enforcement middleware
5. Rate limiting
6. Code expiration

Location: apps/users/tests/test_mfa_email_code.py
"""

import datetime
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.users.models import UserPreferences, TermsAcceptance, MFAEmailCode

User = get_user_model()


class MFAEmailCodeTestMixin:
    """Common setup for MFA email code tests."""

    def create_user(self, email='test@example.com', password='testpass123', is_staff=False):
        """Create a test user with terms accepted and onboarding complete."""
        user = User.objects.create_user(email=email, password=password)
        user.is_staff = is_staff
        user.save()
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user


# =============================================================================
# MFA EMAIL CODE MODEL TESTS
# =============================================================================

class MFAEmailCodeModelTest(MFAEmailCodeTestMixin, TestCase):
    """Test MFAEmailCode model."""

    def test_generate_code_is_six_digits(self):
        """Generated code is exactly 6 digits."""
        code = MFAEmailCode.generate_code()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    def test_generate_code_is_random(self):
        """Generated codes are random (not all the same)."""
        codes = [MFAEmailCode.generate_code() for _ in range(10)]
        # At least some should be different
        self.assertGreater(len(set(codes)), 1)

    def test_create_for_user_success(self):
        """Can create a code for a user."""
        user = self.create_user()
        mfa_code, error = MFAEmailCode.create_for_user(user, '127.0.0.1')

        self.assertIsNone(error)
        self.assertIsNotNone(mfa_code)
        self.assertEqual(mfa_code.user, user)
        self.assertEqual(len(mfa_code.code), 6)
        self.assertFalse(mfa_code.used)
        self.assertEqual(mfa_code.ip_address, '127.0.0.1')

    def test_code_expires_in_10_minutes(self):
        """Code expires 10 minutes after creation."""
        user = self.create_user()
        mfa_code, _ = MFAEmailCode.create_for_user(user)

        expected_expiry = timezone.now() + datetime.timedelta(minutes=10)
        # Allow 1 second tolerance
        self.assertAlmostEqual(
            mfa_code.expires_at.timestamp(),
            expected_expiry.timestamp(),
            delta=1
        )

    def test_is_expired_before_expiry(self):
        """is_expired returns False before expiration."""
        user = self.create_user()
        mfa_code, _ = MFAEmailCode.create_for_user(user)

        self.assertFalse(mfa_code.is_expired)

    def test_is_expired_after_expiry(self):
        """is_expired returns True after expiration."""
        user = self.create_user()
        mfa_code, _ = MFAEmailCode.create_for_user(user)

        # Set expiry to the past
        mfa_code.expires_at = timezone.now() - datetime.timedelta(minutes=1)
        mfa_code.save()

        self.assertTrue(mfa_code.is_expired)

    def test_is_valid_for_fresh_code(self):
        """is_valid returns True for fresh, unused code."""
        user = self.create_user()
        mfa_code, _ = MFAEmailCode.create_for_user(user)

        self.assertTrue(mfa_code.is_valid)

    def test_is_valid_false_for_used_code(self):
        """is_valid returns False for used code."""
        user = self.create_user()
        mfa_code, _ = MFAEmailCode.create_for_user(user)
        mfa_code.mark_used()

        self.assertFalse(mfa_code.is_valid)

    def test_is_valid_false_for_expired_code(self):
        """is_valid returns False for expired code."""
        user = self.create_user()
        mfa_code, _ = MFAEmailCode.create_for_user(user)
        mfa_code.expires_at = timezone.now() - datetime.timedelta(minutes=1)
        mfa_code.save()

        self.assertFalse(mfa_code.is_valid)

    def test_mark_used(self):
        """mark_used sets used flag and timestamp."""
        user = self.create_user()
        mfa_code, _ = MFAEmailCode.create_for_user(user)
        mfa_code.mark_used()

        self.assertTrue(mfa_code.used)
        self.assertIsNotNone(mfa_code.used_at)

    def test_verify_code_success(self):
        """verify_code returns True for valid code."""
        user = self.create_user()
        mfa_code, _ = MFAEmailCode.create_for_user(user)

        result = MFAEmailCode.verify_code(user, mfa_code.code)

        self.assertTrue(result)
        mfa_code.refresh_from_db()
        self.assertTrue(mfa_code.used)

    def test_verify_code_wrong_code(self):
        """verify_code returns False for wrong code."""
        user = self.create_user()
        MFAEmailCode.create_for_user(user)

        result = MFAEmailCode.verify_code(user, '000000')

        self.assertFalse(result)

    def test_verify_code_expired(self):
        """verify_code returns False for expired code."""
        user = self.create_user()
        mfa_code, _ = MFAEmailCode.create_for_user(user)
        mfa_code.expires_at = timezone.now() - datetime.timedelta(minutes=1)
        mfa_code.save()

        result = MFAEmailCode.verify_code(user, mfa_code.code)

        self.assertFalse(result)

    def test_verify_code_already_used(self):
        """verify_code returns False for already used code."""
        user = self.create_user()
        mfa_code, _ = MFAEmailCode.create_for_user(user)
        code = mfa_code.code

        # Use it once
        MFAEmailCode.verify_code(user, code)

        # Try to use it again
        result = MFAEmailCode.verify_code(user, code)
        self.assertFalse(result)

    def test_rate_limiting_blocks_after_5_codes(self):
        """Creating more than 5 codes per hour is blocked."""
        user = self.create_user()

        # Create 5 codes (should succeed)
        for i in range(5):
            mfa_code, error = MFAEmailCode.create_for_user(user)
            self.assertIsNone(error, f"Code {i+1} should succeed")

        # 6th code should fail
        mfa_code, error = MFAEmailCode.create_for_user(user)
        self.assertIsNone(mfa_code)
        self.assertIn("Too many code requests", error)

    def test_previous_codes_invalidated_on_new_request(self):
        """Creating a new code invalidates previous unused codes."""
        user = self.create_user()

        mfa_code1, _ = MFAEmailCode.create_for_user(user)
        old_code = mfa_code1.code

        mfa_code2, _ = MFAEmailCode.create_for_user(user)

        # Old code should be marked as used
        mfa_code1.refresh_from_db()
        self.assertTrue(mfa_code1.used)

        # Old code should not verify
        result = MFAEmailCode.verify_code(user, old_code)
        self.assertFalse(result)

    def test_str_representation(self):
        """String representation is informative."""
        user = self.create_user()
        mfa_code, _ = MFAEmailCode.create_for_user(user)

        str_repr = str(mfa_code)
        self.assertIn(user.email, str_repr)
        self.assertIn(mfa_code.code, str_repr)
        self.assertIn('valid', str_repr)


# =============================================================================
# MFA EMAIL CODE ENDPOINT TESTS
# =============================================================================

class MFAEmailCodeSendViewTest(MFAEmailCodeTestMixin, TestCase):
    """Test MFA email code send endpoint."""

    def test_send_code_requires_login(self):
        """Send code endpoint requires authentication."""
        client = Client()
        response = client.post(reverse('users:mfa_email_send'))

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    @patch('apps.users.views.send_mail')
    def test_send_code_success(self, mock_send_mail):
        """Send code endpoint sends email and returns success."""
        mock_send_mail.return_value = 1  # 1 email sent

        user = self.create_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('users:mfa_email_send'),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('sent', data['message'].lower())

        # Verify email was sent
        mock_send_mail.assert_called_once()
        call_kwargs = mock_send_mail.call_args[1]
        self.assertIn(user.email, call_kwargs['recipient_list'])

    @patch('apps.users.views.send_mail')
    def test_send_code_rate_limited(self, mock_send_mail):
        """Send code endpoint respects rate limiting."""
        mock_send_mail.return_value = 1

        user = self.create_user()
        client = Client()
        client.force_login(user)

        # Send 5 codes
        for _ in range(5):
            client.post(reverse('users:mfa_email_send'), content_type='application/json')

        # 6th should be rate limited
        response = client.post(
            reverse('users:mfa_email_send'),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 429)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('too many', data['error'].lower())


class MFAEmailCodeVerifyViewTest(MFAEmailCodeTestMixin, TestCase):
    """Test MFA email code verify endpoint."""

    def test_verify_code_requires_login(self):
        """Verify code endpoint requires authentication."""
        client = Client()
        response = client.post(
            reverse('users:mfa_email_verify'),
            data='{"code": "123456"}',
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_verify_code_success(self):
        """Verify code endpoint accepts valid code."""
        user = self.create_user()
        mfa_code, _ = MFAEmailCode.create_for_user(user)

        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('users:mfa_email_verify'),
            data=f'{{"code": "{mfa_code.code}"}}',
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        # Check session is marked as MFA verified
        self.assertTrue(client.session.get('mfa_verified'))

    def test_verify_code_invalid(self):
        """Verify code endpoint rejects invalid code."""
        user = self.create_user()
        MFAEmailCode.create_for_user(user)

        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('users:mfa_email_verify'),
            data='{"code": "000000"}',
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('invalid', data['error'].lower())

    def test_verify_code_missing_code(self):
        """Verify code endpoint requires code field."""
        user = self.create_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('users:mfa_email_verify'),
            data='{}',
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])

    def test_verify_code_wrong_format(self):
        """Verify code endpoint rejects non-6-digit codes."""
        user = self.create_user()
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('users:mfa_email_verify'),
            data='{"code": "12345"}',  # Only 5 digits
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])


# =============================================================================
# MFA ENFORCEMENT MIDDLEWARE TESTS
# =============================================================================

class MFAEnforcementMiddlewareTest(MFAEmailCodeTestMixin, TestCase):
    """Test MFA enforcement middleware."""

    def test_exempt_user_not_redirected(self):
        """User in exempt list is not redirected to MFA."""
        # Create user with exempt email
        user = self.create_user(email='dannyjenkins71@gmail.com')

        client = Client()
        client.force_login(user)

        response = client.get(reverse('dashboard:home'))

        # Should access dashboard directly, not redirect to MFA
        self.assertNotEqual(response.status_code, 302)

    def test_required_user_redirected_to_mfa(self):
        """User in required list is redirected to MFA page."""
        # Create user with required email
        user = self.create_user(email='heatherjenkins74@gmail.com')

        client = Client()
        client.force_login(user)

        response = client.get(reverse('dashboard:home'))

        # Should redirect to MFA required page
        self.assertEqual(response.status_code, 302)
        self.assertIn('mfa-required', response.url)

    def test_staff_user_redirected_to_mfa(self):
        """Staff user is redirected to MFA page."""
        user = self.create_user(is_staff=True)

        client = Client()
        client.force_login(user)

        response = client.get(reverse('dashboard:home'))

        # Should redirect to MFA required page
        self.assertEqual(response.status_code, 302)
        self.assertIn('mfa-required', response.url)

    def test_regular_user_not_redirected(self):
        """Regular user (not in required list, not staff) is not redirected."""
        user = self.create_user(email='regular@example.com')

        client = Client()
        client.force_login(user)

        response = client.get(reverse('dashboard:home'))

        # Should access dashboard directly
        self.assertNotEqual(response.status_code, 302)

    def test_mfa_verified_session_allows_access(self):
        """User with mfa_verified in session can access app."""
        user = self.create_user(email='heatherjenkins74@gmail.com')

        client = Client()
        client.force_login(user)

        # Simulate MFA verification
        session = client.session
        session['mfa_verified'] = True
        session.save()

        response = client.get(reverse('dashboard:home'))

        # Should access dashboard directly
        self.assertNotEqual(response.status_code, 302)

    def test_exempt_paths_accessible(self):
        """Exempt paths are accessible without MFA verification."""
        user = self.create_user(email='heatherjenkins74@gmail.com')

        client = Client()
        client.force_login(user)

        # MFA page itself should be accessible
        response = client.get(reverse('users:mfa_required'))
        self.assertEqual(response.status_code, 200)

        # Email send endpoint should be accessible
        response = client.post(
            reverse('users:mfa_email_send'),
            content_type='application/json'
        )
        # Should get 200 or 500 (email might fail), not redirect
        self.assertIn(response.status_code, [200, 500])


# =============================================================================
# MFA REQUIRED PAGE TESTS
# =============================================================================

class MFARequiredViewTest(MFAEmailCodeTestMixin, TestCase):
    """Test MFA required page."""

    def test_shows_both_options(self):
        """MFA required page shows both email and biometric options."""
        user = self.create_user(email='heatherjenkins74@gmail.com')

        client = Client()
        client.force_login(user)

        response = client.get(reverse('users:mfa_required'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Check for email option
        self.assertIn('Email Verification Code', content)
        self.assertIn('Send Code', content)

        # Check for biometric option
        self.assertIn('Biometric Authentication', content)

    def test_redirects_if_already_verified(self):
        """Redirects to dashboard if already MFA verified."""
        user = self.create_user(email='heatherjenkins74@gmail.com')

        client = Client()
        client.force_login(user)

        # Simulate MFA verification
        session = client.session
        session['mfa_verified'] = True
        session.save()

        response = client.get(reverse('users:mfa_required'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('dashboard', response.url)
