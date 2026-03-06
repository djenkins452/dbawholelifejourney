"""
Tests for Mobile API Views

Tests token exchange, health ingestion, and device management endpoints.
"""

import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase
from django.utils import timezone

from apps.health.models import BodyCompositionEntry, GlucoseEntry, SleepEntry, StepsEntry, WeightEntry
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

    @patch("apps.health.tasks.build_user_health_summary")
    def test_ingest_queues_summary_rebuild(self, mock_task):
        """Successful ingest queues async summary rebuild for affected dates."""
        response = self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({
                "metrics": [
                    {
                        "type": "steps",
                        "date": "2024-01-15",
                        "value": 9000,
                        "source": "apple_health",
                        "sync_id": "steps-rebuild-test",
                    },
                    {
                        "type": "steps",
                        "date": "2024-01-16",
                        "value": 7000,
                        "source": "apple_health",
                        "sync_id": "steps-rebuild-test-2",
                    },
                ]
            }),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["created"], 2)
        # Verify delay was called for the affected dates
        self.assertTrue(mock_task.delay.called)
        call_dates = {call[0][1] for call in mock_task.delay.call_args_list}
        self.assertIn("2024-01-15", call_dates)
        self.assertIn("2024-01-16", call_dates)


@patch("apps.health.tasks.build_user_health_summary")
class BodyCompositionSyncTests(TestCase):
    """Test that body fat and lean mass ingestion creates BodyCompositionEntry rows."""

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

    def _ingest(self, metrics):
        return self.client.post(
            "/api/mobile/health/ingest/",
            data=json.dumps({"metrics": metrics}),
            content_type="application/json",
            **self._auth_headers(),
        )

    def test_body_fat_creates_bce(self, _mock_task):
        """Ingesting body fat % creates a BodyCompositionEntry."""
        response = self._ingest([{
            "type": "body_fat",
            "date": "2024-03-01",
            "body_fat_percentage": 22.5,
            "source": "apple_health",
            "sync_id": "bf-001",
        }])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)

        bce = BodyCompositionEntry.objects.filter(
            user=self.user, metric_name="body_fat_pct"
        ).first()
        self.assertIsNotNone(bce)
        self.assertEqual(bce.value, Decimal("22.5"))
        self.assertEqual(bce.unit, "pct")
        self.assertEqual(str(bce.measurement_date), "2024-03-01")

    def test_lean_mass_creates_bce(self, _mock_task):
        """Ingesting lean body mass creates a BodyCompositionEntry."""
        response = self._ingest([{
            "type": "lean_body_mass",
            "date": "2024-03-01",
            "lean_mass_value": 145.3,
            "lean_mass_unit": "lb",
            "source": "apple_health",
            "sync_id": "lm-001",
        }])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)

        bce = BodyCompositionEntry.objects.filter(
            user=self.user, metric_name="lean_mass"
        ).first()
        self.assertIsNotNone(bce)
        self.assertEqual(bce.value, Decimal("145.3"))
        self.assertEqual(bce.unit, "lb")

    def test_body_fat_update_updates_bce(self, _mock_task):
        """Updating body fat via sync_id also updates the BCE row."""
        # First ingestion
        self._ingest([{
            "type": "body_fat",
            "date": "2024-03-01",
            "body_fat_percentage": 22.5,
            "source": "apple_health",
            "sync_id": "bf-002",
        }])

        # Second ingestion with updated value
        self._ingest([{
            "type": "body_fat",
            "date": "2024-03-01",
            "body_fat_percentage": 21.8,
            "source": "apple_health",
            "sync_id": "bf-002",
        }])

        # Should have exactly one BCE row with updated value
        bces = BodyCompositionEntry.objects.filter(
            user=self.user,
            metric_name="body_fat_pct",
            measurement_date="2024-03-01",
        )
        self.assertEqual(bces.count(), 1)
        self.assertEqual(bces.first().value, Decimal("21.8"))

    def test_lean_mass_kg_converted_in_bce(self, _mock_task):
        """Lean mass in kg is converted to lb in the BCE row."""
        self._ingest([{
            "type": "lean_body_mass",
            "date": "2024-03-01",
            "lean_mass_value": 60.0,
            "lean_mass_unit": "kg",
            "source": "apple_health",
            "sync_id": "lm-002",
        }])

        bce = BodyCompositionEntry.objects.get(
            user=self.user, metric_name="lean_mass"
        )
        # 60 kg * 2.20462 = 132.2772
        self.assertAlmostEqual(float(bce.value), 132.28, places=1)
        self.assertEqual(bce.unit, "lb")

    def test_body_fat_date_match_creates_bce(self, _mock_task):
        """Body fat update via date match also creates BCE."""
        # Create a weight entry for this date first
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("180"),
            unit="lb",
            recorded_at=timezone.make_aware(
                timezone.datetime(2024, 3, 1, 12, 0, 0)
            ),
            source="apple_health",
            sync_id="w-100",
        )

        # Ingest body fat with different sync_id (will match by date)
        self._ingest([{
            "type": "body_fat",
            "date": "2024-03-01",
            "body_fat_percentage": 23.0,
            "source": "apple_health",
            "sync_id": "bf-date-match",
        }])

        bce = BodyCompositionEntry.objects.filter(
            user=self.user, metric_name="body_fat_pct"
        ).first()
        self.assertIsNotNone(bce)
        self.assertEqual(bce.value, Decimal("23.0"))

    def test_body_fat_skipped_no_duplicate_bce(self, _mock_task):
        """When body fat is skipped (same value), no new BCE is created."""
        # First ingestion
        self._ingest([{
            "type": "body_fat",
            "date": "2024-03-01",
            "body_fat_percentage": 22.5,
            "source": "apple_health",
            "sync_id": "bf-skip",
        }])

        bce_count_before = BodyCompositionEntry.objects.filter(
            user=self.user, metric_name="body_fat_pct"
        ).count()

        # Same value again — should be skipped
        response = self._ingest([{
            "type": "body_fat",
            "date": "2024-03-01",
            "body_fat_percentage": 22.5,
            "source": "apple_health",
            "sync_id": "bf-skip",
        }])

        self.assertEqual(response.json()["skipped"], 1)

        bce_count_after = BodyCompositionEntry.objects.filter(
            user=self.user, metric_name="body_fat_pct"
        ).count()
        self.assertEqual(bce_count_before, bce_count_after)


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


class ContactImportTests(TestCase):
    """Test single-contact import from iOS contact picker."""

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

    def _post_contact(self, data, **extra_headers):
        headers = {**self._auth_headers(), **extra_headers}
        return self.client.post(
            "/api/mobile/contacts/import/",
            data=json.dumps(data),
            content_type="application/json",
            **headers,
        )

    def test_import_creates_person(self):
        """Importing a new contact creates a Person."""
        response = self._post_contact({
            "first_name": "Heather",
            "last_name": "Jenkins",
            "phone": "555-123-4567",
            "email": "heather@email.com",
        })

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["status"], "created")
        self.assertEqual(data["person"]["first_name"], "Heather")
        self.assertEqual(data["person"]["last_name"], "Jenkins")
        self.assertEqual(data["person"]["phone"], "555-123-4567")
        self.assertEqual(data["person"]["email"], "heather@email.com")
        self.assertEqual(data["person"]["relationship_type"], "other")

        # Verify Person exists in DB
        from apps.relationships.models import Person
        person = Person.objects.get(id=data["person"]["id"])
        self.assertEqual(person.owner, self.user)
        self.assertEqual(person.first_name, "Heather")

    def test_import_deduplicates(self):
        """Importing a duplicate returns the existing Person."""
        from apps.relationships.models import Person
        existing = Person.objects.create(
            owner=self.user,
            first_name="Heather",
            last_name="Jenkins",
            phone="555-000-0000",
            relationship_type="family",
        )

        response = self._post_contact({
            "first_name": "Heather",
            "last_name": "Jenkins",
            "phone": "555-123-4567",
            "email": "heather@email.com",
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "existing")
        self.assertEqual(data["person"]["id"], existing.id)
        # Should NOT overwrite existing data
        self.assertEqual(data["person"]["phone"], "555-000-0000")
        self.assertEqual(data["person"]["relationship_type"], "family")

    def test_import_dedup_case_insensitive(self):
        """Deduplication is case-insensitive."""
        from apps.relationships.models import Person
        existing = Person.objects.create(
            owner=self.user,
            first_name="heather",
            last_name="jenkins",
        )

        response = self._post_contact({
            "first_name": "HEATHER",
            "last_name": "JENKINS",
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "existing")
        self.assertEqual(data["person"]["id"], existing.id)

    def test_import_first_name_only(self):
        """Can import a contact with only a first name."""
        response = self._post_contact({
            "first_name": "Madonna",
        })

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["person"]["first_name"], "Madonna")
        self.assertEqual(data["person"]["last_name"], "")

    def test_import_requires_first_name(self):
        """Import fails without first_name."""
        response = self._post_contact({
            "last_name": "Jenkins",
        })

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("first_name", data["error"])

    def test_import_rejects_invalid_email(self):
        """Import fails with invalid email."""
        response = self._post_contact({
            "first_name": "Heather",
            "email": "not-an-email",
        })

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("email", data["error"].lower())

    def test_import_requires_auth(self):
        """Import endpoint requires Bearer token."""
        response = self.client.post(
            "/api/mobile/contacts/import/",
            data=json.dumps({"first_name": "Test"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    def test_import_rejects_invalid_token(self):
        """Import endpoint rejects invalid Bearer token."""
        response = self.client.post(
            "/api/mobile/contacts/import/",
            data=json.dumps({"first_name": "Test"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer invalid-token",
        )

        self.assertEqual(response.status_code, 401)

    def test_import_rejects_invalid_json(self):
        """Import endpoint rejects invalid JSON body."""
        response = self.client.post(
            "/api/mobile/contacts/import/",
            data="not json",
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid JSON", response.json()["error"])

    def test_import_user_isolation(self):
        """User A cannot see User B's contacts in dedup check."""
        from apps.relationships.models import Person
        other_user = User.objects.create_user(
            email="other@example.com",
            password="testpass123",
        )
        Person.objects.create(
            owner=other_user,
            first_name="Heather",
            last_name="Jenkins",
        )

        # Same name but different owner — should create, not dedup
        response = self._post_contact({
            "first_name": "Heather",
            "last_name": "Jenkins",
        })

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["status"], "created")

    def test_import_optional_fields_nullable(self):
        """Phone and email are optional and can be omitted."""
        response = self._post_contact({
            "first_name": "John",
            "last_name": "Doe",
        })

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["person"]["phone"], "")
        self.assertEqual(data["person"]["email"], "")
