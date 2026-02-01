"""
Tests for Mobile App Models

Tests token generation, validation, device management, and audit logging.
"""

import hashlib
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.mobile.models import (
    HealthIngestionRun,
    MobileAPIToken,
    MobileDevice,
    MobileTokenExchangeCode,
    generate_api_token,
    generate_exchange_code,
)
from apps.users.models import User


class TokenGenerationTests(TestCase):
    """Test token and code generation functions."""

    def test_generate_api_token_length(self):
        """API tokens should be 64 characters."""
        token = generate_api_token()
        self.assertEqual(len(token), 64)

    def test_generate_api_token_unique(self):
        """Each generated token should be unique."""
        tokens = {generate_api_token() for _ in range(100)}
        self.assertEqual(len(tokens), 100)

    def test_generate_exchange_code_length(self):
        """Exchange codes should be 32 characters."""
        code = generate_exchange_code()
        self.assertEqual(len(code), 32)


class MobileDeviceModelTests(TestCase):
    """Test MobileDevice model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )

    def test_create_device(self):
        """Can create a mobile device."""
        device = MobileDevice.objects.create(
            user=self.user,
            device_id="test-uuid-12345",
            device_name="Test iPhone",
            device_model="iPhone 15 Pro",
            os_version="iOS 17.2",
            app_version="1.0.0",
        )

        self.assertEqual(device.user, self.user)
        self.assertEqual(device.device_id, "test-uuid-12345")
        self.assertTrue(device.is_active)
        self.assertIsNone(device.last_seen_at)

    def test_device_unique_per_user(self):
        """Device ID must be unique per user."""
        MobileDevice.objects.create(
            user=self.user,
            device_id="test-uuid-12345",
        )

        with self.assertRaises(Exception):
            MobileDevice.objects.create(
                user=self.user,
                device_id="test-uuid-12345",
            )

    def test_update_last_seen(self):
        """update_last_seen() sets timestamp."""
        device = MobileDevice.objects.create(
            user=self.user,
            device_id="test-uuid-12345",
        )

        self.assertIsNone(device.last_seen_at)
        device.update_last_seen()

        device.refresh_from_db()
        self.assertIsNotNone(device.last_seen_at)


class MobileAPITokenModelTests(TestCase):
    """Test MobileAPIToken model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        self.device = MobileDevice.objects.create(
            user=self.user,
            device_id="test-uuid-12345",
        )

    def test_create_token(self):
        """Can create an API token."""
        token, raw_token = MobileAPIToken.create_token(
            user=self.user,
            device=self.device,
        )

        self.assertEqual(token.user, self.user)
        self.assertEqual(token.device, self.device)
        self.assertTrue(token.is_active)
        self.assertEqual(token.token_prefix, raw_token[:8])

        # Hash should match
        expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        self.assertEqual(token.token_hash, expected_hash)

    def test_validate_token_success(self):
        """Valid token returns token object."""
        token, raw_token = MobileAPIToken.create_token(
            user=self.user,
            device=self.device,
        )

        validated = MobileAPIToken.validate_token(raw_token)
        self.assertEqual(validated.id, token.id)
        self.assertEqual(validated.user, self.user)

    def test_validate_token_updates_last_used(self):
        """Validating token updates last_used_at."""
        token, raw_token = MobileAPIToken.create_token(
            user=self.user,
            device=self.device,
        )

        self.assertIsNone(token.last_used_at)

        MobileAPIToken.validate_token(raw_token)

        token.refresh_from_db()
        self.assertIsNotNone(token.last_used_at)

    def test_validate_token_invalid(self):
        """Invalid token returns None."""
        result = MobileAPIToken.validate_token("invalid-token")
        self.assertIsNone(result)

    def test_validate_token_revoked(self):
        """Revoked token returns None."""
        token, raw_token = MobileAPIToken.create_token(
            user=self.user,
            device=self.device,
        )
        token.revoke()

        result = MobileAPIToken.validate_token(raw_token)
        self.assertIsNone(result)

    def test_validate_token_expired(self):
        """Expired token returns None."""
        token, raw_token = MobileAPIToken.create_token(
            user=self.user,
            device=self.device,
            expires_days=0,  # Already expired
        )
        # Force expiration
        token.expires_at = timezone.now() - timedelta(hours=1)
        token.save()

        result = MobileAPIToken.validate_token(raw_token)
        self.assertIsNone(result)

    def test_validate_token_inactive_device(self):
        """Token for inactive device returns None."""
        token, raw_token = MobileAPIToken.create_token(
            user=self.user,
            device=self.device,
        )
        self.device.is_active = False
        self.device.save()

        result = MobileAPIToken.validate_token(raw_token)
        self.assertIsNone(result)

    def test_revoke_token(self):
        """revoke() deactivates token."""
        token, _ = MobileAPIToken.create_token(
            user=self.user,
            device=self.device,
        )

        self.assertTrue(token.is_active)
        token.revoke()

        token.refresh_from_db()
        self.assertFalse(token.is_active)


class MobileTokenExchangeCodeTests(TestCase):
    """Test exchange code model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )

    def test_create_code(self):
        """Can create an exchange code."""
        code = MobileTokenExchangeCode.create_code(self.user)

        self.assertEqual(code.user, self.user)
        self.assertFalse(code.is_used)
        self.assertIsNotNone(code.code)
        self.assertGreater(code.expires_at, timezone.now())

    def test_consume_code_success(self):
        """Can consume a valid code."""
        code = MobileTokenExchangeCode.create_code(self.user)

        result = code.consume("device-123")

        self.assertTrue(result)
        code.refresh_from_db()
        self.assertTrue(code.is_used)
        self.assertIsNotNone(code.used_at)
        self.assertEqual(code.used_by_device_id, "device-123")

    def test_consume_code_already_used(self):
        """Cannot consume an already-used code."""
        code = MobileTokenExchangeCode.create_code(self.user)
        code.consume("device-123")

        result = code.consume("device-456")
        self.assertFalse(result)

    def test_consume_code_expired(self):
        """Cannot consume an expired code."""
        code = MobileTokenExchangeCode.create_code(self.user)
        code.expires_at = timezone.now() - timedelta(minutes=1)
        code.save()

        result = code.consume("device-123")
        self.assertFalse(result)


class HealthIngestionRunTests(TestCase):
    """Test health ingestion audit logging."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        self.device = MobileDevice.objects.create(
            user=self.user,
            device_id="test-uuid-12345",
        )

    def test_create_ingestion_run(self):
        """Can create an ingestion run."""
        run = HealthIngestionRun.objects.create(
            user=self.user,
            device=self.device,
            payload_size_bytes=1024,
            metrics_received=10,
        )

        self.assertEqual(run.status, "pending")
        self.assertEqual(run.metrics_received, 10)

    def test_mark_processing(self):
        """mark_processing() updates status."""
        run = HealthIngestionRun.objects.create(
            user=self.user,
            device=self.device,
        )

        run.mark_processing()

        run.refresh_from_db()
        self.assertEqual(run.status, "processing")
        self.assertIsNotNone(run.started_at)

    def test_mark_completed(self):
        """mark_completed() updates status and stats."""
        run = HealthIngestionRun.objects.create(
            user=self.user,
            device=self.device,
        )
        run.mark_processing()

        run.mark_completed(created=5, updated=3, skipped=2)

        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.metrics_created, 5)
        self.assertEqual(run.metrics_updated, 3)
        self.assertEqual(run.metrics_skipped, 2)
        self.assertIsNotNone(run.completed_at)

    def test_mark_failed(self):
        """mark_failed() updates status with error."""
        run = HealthIngestionRun.objects.create(
            user=self.user,
            device=self.device,
        )

        run.mark_failed("Something went wrong")

        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.error_message, "Something went wrong")
