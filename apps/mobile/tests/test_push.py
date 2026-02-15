"""
Tests for Mobile Push Notification API Endpoints.

Tests push token registration and unregistration via the mobile API.
"""

import json

from django.test import Client, TestCase

from apps.mobile.models import MobileAPIToken, MobileDevice
from apps.users.models import User


class PushRegistrationTests(TestCase):
    """Test push token register/unregister mobile API endpoints."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="push_test@example.com",
            password="testpass123",
        )
        self.device = MobileDevice.objects.create(
            user=self.user,
            device_id="push-test-device-uuid",
        )
        self.token, self.raw_token = MobileAPIToken.create_token(
            user=self.user,
            device=self.device,
        )

    def _auth_headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}

    def test_register_push_token(self):
        """POST /api/mobile/push/register/ stores push token on device."""
        response = self.client.post(
            "/api/mobile/push/register/",
            data=json.dumps({"push_token": "abc123hextoken"}),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "registered")
        self.assertEqual(data["device_id"], "push-test-device-uuid")

        self.device.refresh_from_db()
        self.assertEqual(self.device.push_token, "abc123hextoken")
        self.assertTrue(self.device.push_enabled)

    def test_register_does_not_auto_enable_push_pref(self):
        """Registering a push token does NOT auto-enable intelligence_push_enabled."""
        self.assertFalse(self.user.preferences.intelligence_push_enabled)

        self.client.post(
            "/api/mobile/push/register/",
            data=json.dumps({"push_token": "abc123hextoken"}),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.user.preferences.refresh_from_db()
        self.assertFalse(self.user.preferences.intelligence_push_enabled)

    def test_register_updates_existing_token(self):
        """Registering again overwrites the previous push token."""
        self.device.push_token = "old_token"
        self.device.push_enabled = True
        self.device.save()

        self.client.post(
            "/api/mobile/push/register/",
            data=json.dumps({"push_token": "new_token"}),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.device.refresh_from_db()
        self.assertEqual(self.device.push_token, "new_token")
        self.assertTrue(self.device.push_enabled)

    def test_unregister_push_token(self):
        """POST /api/mobile/push/unregister/ clears push token."""
        self.device.push_token = "abc123"
        self.device.push_enabled = True
        self.device.save()

        response = self.client.post(
            "/api/mobile/push/unregister/",
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "unregistered")

        self.device.refresh_from_db()
        self.assertEqual(self.device.push_token, "")
        self.assertFalse(self.device.push_enabled)

    def test_register_requires_auth(self):
        """Register endpoint requires Bearer token authentication."""
        response = self.client.post(
            "/api/mobile/push/register/",
            data=json.dumps({"push_token": "abc123"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_unregister_requires_auth(self):
        """Unregister endpoint requires Bearer token authentication."""
        response = self.client.post(
            "/api/mobile/push/unregister/",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_register_empty_token_rejected(self):
        """Empty push_token is rejected."""
        response = self.client.post(
            "/api/mobile/push/register/",
            data=json.dumps({"push_token": ""}),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "invalid_token")

    def test_register_missing_token_rejected(self):
        """Missing push_token field is rejected."""
        response = self.client.post(
            "/api/mobile/push/register/",
            data=json.dumps({}),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 400)

    def test_register_invalid_json_rejected(self):
        """Invalid JSON body is rejected."""
        response = self.client.post(
            "/api/mobile/push/register/",
            data="not json",
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "invalid_json")

    def test_register_token_too_long_rejected(self):
        """Push token longer than 255 chars is rejected."""
        response = self.client.post(
            "/api/mobile/push/register/",
            data=json.dumps({"push_token": "a" * 256}),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 400)

    def test_register_only_accepts_post(self):
        """Register endpoint only accepts POST."""
        response = self.client.get(
            "/api/mobile/push/register/",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 405)
