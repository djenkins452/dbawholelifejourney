"""
Biometric Login (WebAuthn) Tests

Tests for:
1. WebAuthnCredential model
2. Biometric check endpoint (login page)
3. Biometric credentials list (preferences page)
4. Registration flow (begin/complete)
5. Authentication flow (begin/complete)
6. Credential deletion
7. UserPreferences.biometric_login_enabled field

Location: apps/users/tests/test_biometric_login.py
"""

import base64
import json
import secrets
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.users.models import UserPreferences, TermsAcceptance, WebAuthnCredential

User = get_user_model()


class BiometricTestMixin:
    """Common setup for biometric tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        """Create a test user with terms accepted and onboarding complete."""
        user = User.objects.create_user(email=email, password=password)
        TermsAcceptance.objects.create(user=user, terms_version='1.0')
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def create_credential(self, user, device_name='Test Device'):
        """Create a test WebAuthn credential."""
        credential_id = secrets.token_bytes(32)
        credential_id_b64 = base64.urlsafe_b64encode(credential_id).rstrip(b'=').decode()
        public_key = secrets.token_bytes(64)

        return WebAuthnCredential.objects.create(
            user=user,
            credential_id=credential_id,
            credential_id_b64=credential_id_b64,
            public_key=public_key,
            device_name=device_name,
        )


# =============================================================================
# WEBAUTHN CREDENTIAL MODEL TESTS
# =============================================================================

class WebAuthnCredentialModelTest(BiometricTestMixin, TestCase):
    """Test WebAuthnCredential model."""

    def test_create_credential(self):
        """Can create a WebAuthn credential."""
        user = self.create_user()
        cred = self.create_credential(user)

        self.assertEqual(cred.user, user)
        self.assertEqual(cred.device_name, 'Test Device')
        self.assertEqual(cred.sign_count, 0)
        self.assertIsNone(cred.last_used_at)

    def test_credential_str(self):
        """Credential string representation is correct."""
        user = self.create_user()
        cred = self.create_credential(user, device_name='iPhone 15')

        self.assertIn('test@example.com', str(cred))
        self.assertIn('iPhone 15', str(cred))

    def test_credential_str_unknown_device(self):
        """Credential string handles empty device name."""
        user = self.create_user()
        cred = self.create_credential(user, device_name='')

        self.assertIn('Unknown device', str(cred))

    def test_user_can_have_multiple_credentials(self):
        """User can register multiple biometric devices."""
        user = self.create_user()
        cred1 = self.create_credential(user, device_name='iPhone')
        cred2 = self.create_credential(user, device_name='iPad')

        self.assertEqual(user.webauthn_credentials.count(), 2)

    def test_credentials_ordered_by_created_at_desc(self):
        """Credentials are ordered newest first."""
        user = self.create_user()
        cred1 = self.create_credential(user, device_name='First')
        cred2 = self.create_credential(user, device_name='Second')

        creds = list(user.webauthn_credentials.all())
        self.assertEqual(creds[0], cred2)  # Newest first
        self.assertEqual(creds[1], cred1)


# =============================================================================
# BIOMETRIC PREFERENCE TESTS
# =============================================================================

class BiometricPreferenceTest(BiometricTestMixin, TestCase):
    """Test biometric_login_enabled preference."""

    def test_biometric_disabled_by_default(self):
        """Biometric login is disabled by default."""
        user = self.create_user()
        self.assertFalse(user.preferences.biometric_login_enabled)

    def test_enable_biometric(self):
        """Can enable biometric login."""
        user = self.create_user()
        user.preferences.biometric_login_enabled = True
        user.preferences.save()

        user.preferences.refresh_from_db()
        self.assertTrue(user.preferences.biometric_login_enabled)

    def test_biometric_in_preferences_form(self):
        """Biometric field is in preferences form."""
        from apps.users.forms import PreferencesForm
        form = PreferencesForm()
        self.assertIn('biometric_login_enabled', form.fields)


# =============================================================================
# BIOMETRIC CHECK ENDPOINT TESTS
# =============================================================================

class BiometricCheckViewTest(BiometricTestMixin, TestCase):
    """Test /user/biometric/check/ endpoint."""

    def test_no_credentials_returns_false(self):
        """Returns available=false when no credentials exist."""
        response = self.client.get(reverse('users:biometric_check'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['available'])

    def test_with_credentials_returns_true(self):
        """Returns available=true when credentials exist."""
        user = self.create_user()
        self.create_credential(user)

        response = self.client.get(reverse('users:biometric_check'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['available'])

    def test_no_authentication_required(self):
        """Endpoint does not require authentication."""
        # Should work without logging in
        response = self.client.get(reverse('users:biometric_check'))
        self.assertEqual(response.status_code, 200)


# =============================================================================
# BIOMETRIC CREDENTIALS LIST TESTS
# =============================================================================

class BiometricCredentialsViewTest(BiometricTestMixin, TestCase):
    """Test /user/biometric/credentials/ endpoint."""

    def test_requires_authentication(self):
        """Requires user to be logged in."""
        response = self.client.get(reverse('users:biometric_credentials'))
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url.lower())

    def test_returns_empty_list_for_new_user(self):
        """Returns empty list for user with no credentials."""
        user = self.create_user()
        self.client.login(email='test@example.com', password='testpass123')

        response = self.client.get(reverse('users:biometric_credentials'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['credentials'], [])

    def test_returns_user_credentials(self):
        """Returns user's credentials."""
        user = self.create_user()
        cred = self.create_credential(user, device_name='My iPhone')
        self.client.login(email='test@example.com', password='testpass123')

        response = self.client.get(reverse('users:biometric_credentials'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['credentials']), 1)
        self.assertEqual(data['credentials'][0]['device_name'], 'My iPhone')

    def test_does_not_return_other_users_credentials(self):
        """Does not return credentials from other users."""
        user1 = self.create_user(email='user1@example.com')
        user2 = self.create_user(email='user2@example.com')

        self.create_credential(user1, device_name='User1 Device')
        self.create_credential(user2, device_name='User2 Device')

        self.client.login(email='user1@example.com', password='testpass123')

        response = self.client.get(reverse('users:biometric_credentials'))
        data = response.json()

        self.assertEqual(len(data['credentials']), 1)
        self.assertEqual(data['credentials'][0]['device_name'], 'User1 Device')


# =============================================================================
# REGISTRATION BEGIN TESTS
# =============================================================================

class BiometricRegisterBeginViewTest(BiometricTestMixin, TestCase):
    """Test /user/biometric/register/begin/ endpoint."""

    def test_requires_authentication(self):
        """Requires user to be logged in."""
        response = self.client.post(
            reverse('users:biometric_register_begin'),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 302)

    def test_returns_registration_options(self):
        """Returns WebAuthn registration options."""
        user = self.create_user()
        self.client.login(email='test@example.com', password='testpass123')

        response = self.client.post(
            reverse('users:biometric_register_begin'),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check required fields
        self.assertIn('challenge', data)
        self.assertIn('rp', data)
        self.assertIn('user', data)
        self.assertIn('pubKeyCredParams', data)

        # Check RP info
        self.assertEqual(data['rp']['name'], 'Whole Life Journey')

        # Check user info
        self.assertEqual(data['user']['name'], 'test@example.com')

    def test_stores_challenge_in_session(self):
        """Stores challenge in session for verification."""
        user = self.create_user()
        self.client.login(email='test@example.com', password='testpass123')

        response = self.client.post(
            reverse('users:biometric_register_begin'),
            content_type='application/json'
        )

        self.assertIn('webauthn_challenge', self.client.session)

    def test_excludes_existing_credentials(self):
        """Excludes user's existing credentials to prevent re-registration."""
        user = self.create_user()
        cred = self.create_credential(user)
        self.client.login(email='test@example.com', password='testpass123')

        response = self.client.post(
            reverse('users:biometric_register_begin'),
            content_type='application/json'
        )

        data = response.json()
        self.assertEqual(len(data['excludeCredentials']), 1)
        self.assertEqual(data['excludeCredentials'][0]['id'], cred.credential_id_b64)


# =============================================================================
# REGISTRATION COMPLETE TESTS
# =============================================================================

class BiometricRegisterCompleteViewTest(BiometricTestMixin, TestCase):
    """Test /user/biometric/register/complete/ endpoint."""

    def setUp(self):
        self.user = self.create_user()
        self.client.login(email='test@example.com', password='testpass123')

        # Start registration to get challenge
        self.client.post(
            reverse('users:biometric_register_begin'),
            content_type='application/json'
        )

    def test_requires_active_challenge(self):
        """Fails without an active registration challenge."""
        # Clear the challenge
        session = self.client.session
        del session['webauthn_challenge']
        session.save()

        response = self.client.post(
            reverse('users:biometric_register_complete'),
            data=json.dumps({'rawId': 'test'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('No active registration challenge', response.json()['error'])

    def test_requires_credential_id(self):
        """Fails without credential ID."""
        response = self.client.post(
            reverse('users:biometric_register_complete'),
            data=json.dumps({}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Missing credential ID', response.json()['error'])


# =============================================================================
# LOGIN BEGIN TESTS
# =============================================================================

class BiometricLoginBeginViewTest(BiometricTestMixin, TestCase):
    """Test /user/biometric/login/begin/ endpoint."""

    def test_no_authentication_required(self):
        """Does not require authentication (it's for logging in!)."""
        user = self.create_user()
        self.create_credential(user)

        response = self.client.post(
            reverse('users:biometric_login_begin'),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)

    def test_returns_authentication_options(self):
        """Returns WebAuthn authentication options."""
        user = self.create_user()
        cred = self.create_credential(user)

        response = self.client.post(
            reverse('users:biometric_login_begin'),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn('challenge', data)
        self.assertIn('allowCredentials', data)
        self.assertIn('userVerification', data)

    def test_includes_all_registered_credentials(self):
        """Includes all registered credentials for discovery."""
        user1 = self.create_user(email='user1@example.com')
        user2 = self.create_user(email='user2@example.com')
        cred1 = self.create_credential(user1)
        cred2 = self.create_credential(user2)

        response = self.client.post(
            reverse('users:biometric_login_begin'),
            content_type='application/json'
        )

        data = response.json()
        credential_ids = [c['id'] for c in data['allowCredentials']]

        self.assertIn(cred1.credential_id_b64, credential_ids)
        self.assertIn(cred2.credential_id_b64, credential_ids)

    def test_stores_challenge_in_session(self):
        """Stores challenge in session for verification."""
        user = self.create_user()
        self.create_credential(user)

        response = self.client.post(
            reverse('users:biometric_login_begin'),
            content_type='application/json'
        )

        self.assertIn('webauthn_login_challenge', self.client.session)


# =============================================================================
# LOGIN COMPLETE TESTS
# =============================================================================

class BiometricLoginCompleteViewTest(BiometricTestMixin, TestCase):
    """Test /user/biometric/login/complete/ endpoint."""

    def setUp(self):
        self.user = self.create_user()
        self.cred = self.create_credential(self.user)

        # Start login to get challenge
        self.client.post(
            reverse('users:biometric_login_begin'),
            content_type='application/json'
        )

    def test_requires_active_challenge(self):
        """Fails without an active login challenge."""
        session = self.client.session
        del session['webauthn_login_challenge']
        session.save()

        response = self.client.post(
            reverse('users:biometric_login_complete'),
            data=json.dumps({'rawId': self.cred.credential_id_b64}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('No active authentication challenge', response.json()['error'])

    def test_fails_with_unknown_credential(self):
        """Fails with unknown credential ID."""
        response = self.client.post(
            reverse('users:biometric_login_complete'),
            data=json.dumps({
                'rawId': 'unknown_credential_id',
                'response': {
                    'authenticatorData': 'test',
                    'clientDataJSON': 'test',
                    'signature': 'test',
                }
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Unknown credential', response.json()['error'])


# =============================================================================
# CREDENTIAL DELETE TESTS
# =============================================================================

class BiometricDeleteCredentialViewTest(BiometricTestMixin, TestCase):
    """Test /user/biometric/delete/<id>/ endpoint."""

    def test_requires_authentication(self):
        """Requires user to be logged in."""
        user = self.create_user()
        cred = self.create_credential(user)

        response = self.client.post(
            reverse('users:biometric_delete', kwargs={'credential_id': cred.id})
        )

        self.assertEqual(response.status_code, 302)

    def test_can_delete_own_credential(self):
        """User can delete their own credential."""
        user = self.create_user()
        cred = self.create_credential(user)
        self.client.login(email='test@example.com', password='testpass123')

        response = self.client.post(
            reverse('users:biometric_delete', kwargs={'credential_id': cred.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(WebAuthnCredential.objects.filter(id=cred.id).exists())

    def test_cannot_delete_other_users_credential(self):
        """Cannot delete another user's credential."""
        user1 = self.create_user(email='user1@example.com')
        user2 = self.create_user(email='user2@example.com')
        cred = self.create_credential(user1)

        self.client.login(email='user2@example.com', password='testpass123')

        response = self.client.post(
            reverse('users:biometric_delete', kwargs={'credential_id': cred.id})
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(WebAuthnCredential.objects.filter(id=cred.id).exists())

    def test_disables_biometric_when_last_credential_deleted(self):
        """Disables biometric login when user deletes their last credential."""
        user = self.create_user()
        cred = self.create_credential(user)
        user.preferences.biometric_login_enabled = True
        user.preferences.save()

        self.client.login(email='test@example.com', password='testpass123')

        response = self.client.post(
            reverse('users:biometric_delete', kwargs={'credential_id': cred.id})
        )

        user.preferences.refresh_from_db()
        self.assertFalse(user.preferences.biometric_login_enabled)

    def test_keeps_biometric_enabled_with_remaining_credentials(self):
        """Keeps biometric enabled if user has other credentials."""
        user = self.create_user()
        cred1 = self.create_credential(user, device_name='iPhone')
        cred2 = self.create_credential(user, device_name='iPad')
        user.preferences.biometric_login_enabled = True
        user.preferences.save()

        self.client.login(email='test@example.com', password='testpass123')

        response = self.client.post(
            reverse('users:biometric_delete', kwargs={'credential_id': cred1.id})
        )

        user.preferences.refresh_from_db()
        self.assertTrue(user.preferences.biometric_login_enabled)
        self.assertEqual(user.webauthn_credentials.count(), 1)
