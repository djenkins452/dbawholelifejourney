"""
Tests for Mobile API Views

Tests token exchange, health ingestion, and device management endpoints.
"""

import json
from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.utils import timezone

from apps.health.models import GlucoseEntry, SleepEntry, StepsEntry, WeightEntry
from apps.mobile.models import (
    HealthIngestionRun,
    MobileAPIToken,
    MobileDevice,
    MobileTokenExchangeCode,
)
from apps.users.models import User


class TokenExchangeTests(TestCase):
    """Test token exchange flow."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )

    def test_generate_exchange_code(self):
        """Logged-in user can generate exchange code."""
        self.client.force_login(self.user)

        response = self.client.post("/api/mobile/generate-code/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("code", data)
        self.assertEqual(data["expires_in"], 300)

        # Code should exist in database
        self.assertTrue(
            MobileTokenExchangeCode.objects.filter(
                user=self.user,
                code=data["code"],
            ).exists()
        )

    def test_generate_exchange_code_requires_auth(self):
        """Generate code requires login."""
        response = self.client.post("/api/mobile/generate-code/")
        # Should redirect to login
        self.assertEqual(response.status_code, 302)

    def test_exchange_token_success(self):
        """Can exchange valid code for token."""
        code = MobileTokenExchangeCode.create_code(self.user)

        response = self.client.post(
            "/api/mobile/token/exchange/",
            data=json.dumps({
                "code": code.code,
                "device_id": "test-device-uuid",
                "device_name": "Test iPhone",
                "device_model": "iPhone 15 Pro",
                "os_version": "iOS 17.2",
                "app_version": "1.0.0",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("token", data)
        self.assertIn("expires_at", data)
        self.assertEqual(data["user"]["email"], "test@example.com")

        # Device should be created
        device = MobileDevice.objects.get(device_id="test-device-uuid")
        self.assertEqual(device.user, self.user)
        self.assertEqual(device.device_name, "Test iPhone")

        # Code should be consumed
        code.refresh_from_db()
        self.assertTrue(code.is_used)

    def test_exchange_token_invalid_code(self):
        """Invalid code returns error."""
        response = self.client.post(
            "/api/mobile/token/exchange/",
            data=json.dumps({
                "code": "invalid-code",
                "device_id": "test-device-uuid",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "invalid_code")

    def test_exchange_token_expired_code(self):
        """Expired code returns error."""
        code = MobileTokenExchangeCode.create_code(self.user)
        code.expires_at = timezone.now() - timedelta(minutes=1)
        code.save()

        response = self.client.post(
            "/api/mobile/token/exchange/",
            data=json.dumps({
                "code": code.code,
                "device_id": "test-device-uuid",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "expired_code")


class HealthIngestionTests(TestCase):
    """Test health data ingestion endpoint."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        self.device = MobileDevice.objects.create(
            user=self.user,
            device_id="test-device-uuid",
        )
        self.token, self.raw_token = MobileAPIToken.create_token(
            user=self.user,
            device=self.device,
        )

    def _auth_headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}

    def test_ingest_steps(self):
        """Can ingest steps data."""
        response = self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({
                "metrics": [
                    {
                        "type": "steps",
                        "date": "2024-01-15",
                        "value": 8500,
                        "source": "apple_health",
                        "sync_id": "steps-123",
                    }
                ]
            }),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["created"], 1)

        # Steps entry should exist
        entry = StepsEntry.objects.get(user=self.user, logged_date="2024-01-15")
        self.assertEqual(entry.count, 8500)
        self.assertEqual(entry.source, "apple_health")

    def test_ingest_weight(self):
        """Can ingest weight data."""
        response = self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({
                "metrics": [
                    {
                        "type": "weight",
                        "date": "2024-01-15",
                        "value": 175.5,
                        "unit": "lb",
                        "source": "apple_health",
                    }
                ]
            }),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["created"], 1)

        # Weight entry should exist
        entry = WeightEntry.objects.filter(user=self.user).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.value, Decimal("175.5"))
        self.assertEqual(entry.unit, "lb")

    def test_ingest_sleep(self):
        """Can ingest sleep data."""
        response = self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({
                "metrics": [
                    {
                        "type": "sleep",
                        "date": "2024-01-15",
                        "bedtime": "2024-01-14T23:00:00Z",
                        "wake_time": "2024-01-15T07:00:00Z",
                        "total_minutes": 480,
                        "deep_minutes": 90,
                        "rem_minutes": 120,
                        "source": "apple_health",
                        "sync_id": "sleep-123",
                    }
                ]
            }),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["created"], 1)

        # Sleep entry should exist
        entry = SleepEntry.objects.get(user=self.user, sleep_date="2024-01-15")
        self.assertEqual(entry.total_duration_minutes, 480)
        self.assertEqual(entry.stage_deep_minutes, 90)
        self.assertEqual(entry.stage_rem_minutes, 120)

    def test_ingest_requires_auth(self):
        """Ingest endpoint requires Bearer token."""
        response = self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({"metrics": []}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    def test_ingest_invalid_token(self):
        """Invalid token returns 401."""
        response = self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({"metrics": []}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer invalid-token",
        )

        self.assertEqual(response.status_code, 401)

    def test_ingest_deduplication_by_sync_id(self):
        """Duplicate sync_id updates instead of creates."""
        # First ingestion
        self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({
                "metrics": [
                    {
                        "type": "steps",
                        "date": "2024-01-15",
                        "value": 8500,
                        "source": "apple_health",
                        "sync_id": "steps-123",
                    }
                ]
            }),
            content_type="application/json",
            **self._auth_headers(),
        )

        # Second ingestion with same sync_id but different value
        response = self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({
                "metrics": [
                    {
                        "type": "steps",
                        "date": "2024-01-15",
                        "value": 9000,
                        "source": "apple_health",
                        "sync_id": "steps-123",
                    }
                ]
            }),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["updated"], 1)
        self.assertEqual(data["created"], 0)

        # Should only have one entry with updated value
        entries = StepsEntry.objects.filter(user=self.user, logged_date="2024-01-15")
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.first().count, 9000)

    def test_ingest_creates_audit_log(self):
        """Ingestion creates audit log entry."""
        self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({
                "metrics": [
                    {
                        "type": "steps",
                        "date": "2024-01-15",
                        "value": 8500,
                        "source": "apple_health",
                    }
                ]
            }),
            content_type="application/json",
            **self._auth_headers(),
        )

        run = HealthIngestionRun.objects.get(user=self.user)
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.metrics_received, 1)
        self.assertEqual(run.metrics_created, 1)

    def test_ingest_validation_error(self):
        """Invalid metric returns error in response."""
        response = self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({
                "metrics": [
                    {
                        "type": "steps",
                        "date": "2024-01-15",
                        "value": -100,  # Invalid: negative
                        "source": "apple_health",
                    }
                ]
            }),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)  # Still 200, errors in response
        data = response.json()
        self.assertEqual(len(data["errors"]), 1)
        self.assertIn("out of range", data["errors"][0]["error"])

    def test_ingest_blood_glucose_with_iso_timestamp(self):
        """Can ingest blood glucose with ISO8601 timestamp format."""
        response = self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({
                "metrics": [
                    {
                        "type": "blood_glucose",
                        "date": "2024-01-15T10:30:00Z",  # ISO timestamp, not just date
                        "glucose_value": 120.5,
                        "glucose_unit": "mg/dL",
                        "source": "apple_health",
                        "sync_id": "glucose-abc123",
                    }
                ]
            }),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["created"], 1)

        # Glucose entry should exist with correct value
        entry = GlucoseEntry.objects.filter(user=self.user).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.value, Decimal("120.5"))
        self.assertEqual(entry.unit, "mg/dL")
        self.assertEqual(entry.source, "apple_health")
        self.assertEqual(entry.sync_id, "glucose-abc123")

    def test_ingest_payload_size_limit(self):
        """Oversized payload is rejected by Django's built-in protection."""
        # Create payload > 1MB
        large_metrics = [
            {"type": "steps", "date": "2024-01-15", "value": 1000}
            for _ in range(50000)
        ]

        response = self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({"metrics": large_metrics}),
            content_type="application/json",
            **self._auth_headers(),
        )

        # Django's DATA_UPLOAD_MAX_MEMORY_SIZE protection returns 400
        # Our view would return 413 if it got through, but Django catches it first
        self.assertIn(response.status_code, [400, 413])


class DeviceManagementTests(TestCase):
    """Test device management endpoints."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        self.device = MobileDevice.objects.create(
            user=self.user,
            device_id="test-device-uuid",
            device_name="Test iPhone",
        )
        self.token, self.raw_token = MobileAPIToken.create_token(
            user=self.user,
            device=self.device,
        )

    def _auth_headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}

    def test_list_devices(self):
        """Can list user's devices."""
        response = self.client.get(
            "/api/mobile/devices/",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["devices"]), 1)
        self.assertEqual(data["devices"][0]["device_name"], "Test iPhone")
        self.assertTrue(data["devices"][0]["is_current"])

    def test_deactivate_device(self):
        """Can deactivate a device."""
        response = self.client.post(
            f"/api/mobile/devices/{self.device.id}/deactivate/",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)

        self.device.refresh_from_db()
        self.assertFalse(self.device.is_active)

        # Token should also be revoked
        self.token.refresh_from_db()
        self.assertFalse(self.token.is_active)


class SyncStatusTests(TestCase):
    """Test sync status endpoint."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        self.device = MobileDevice.objects.create(
            user=self.user,
            device_id="test-device-uuid",
        )
        self.token, self.raw_token = MobileAPIToken.create_token(
            user=self.user,
            device=self.device,
        )

    def _auth_headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_token}"}

    def test_sync_status_empty(self):
        """Sync status works with no data."""
        response = self.client.get(
            "/api/mobile/health/sync-status/",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["last_sync"])
        self.assertIsNone(data["metrics_synced"]["steps"])
