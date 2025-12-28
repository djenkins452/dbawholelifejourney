"""
Scan Models Tests - Tests for scan models.
"""

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.scan.models import ScanConsent, ScanLog
from apps.users.models import TermsAcceptance

User = get_user_model()


class ScanTestMixin:
    """Mixin for scan tests with proper user setup."""

    def create_user(self, email='test@example.com', password='testpass123'):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        return user

    def _accept_terms(self, user):
        TermsAcceptance.objects.create(user=user, terms_version='1.0')

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()


class ScanLogModelTests(ScanTestMixin, TestCase):
    """Tests for the ScanLog model."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_scan_log(self):
        """Test creating a scan log entry."""
        log = ScanLog.objects.create(
            user=self.user,
            status=ScanLog.STATUS_PENDING
        )

        self.assertIsNotNone(log.request_id)
        self.assertEqual(log.status, ScanLog.STATUS_PENDING)
        self.assertEqual(log.user, self.user)

    def test_request_id_is_unique(self):
        """Test that request_id is unique."""
        log1 = ScanLog.objects.create(user=self.user)
        log2 = ScanLog.objects.create(user=self.user)

        self.assertNotEqual(log1.request_id, log2.request_id)

    def test_mark_success(self):
        """Test marking a scan as successful."""
        log = ScanLog.objects.create(
            user=self.user,
            status=ScanLog.STATUS_PENDING
        )

        log.mark_success(
            category='food',
            confidence=0.92,
            items=[{'label': 'Pizza'}],
            processing_time_ms=1500
        )

        log.refresh_from_db()
        self.assertEqual(log.status, ScanLog.STATUS_SUCCESS)
        self.assertEqual(log.category, 'food')
        self.assertEqual(log.confidence, 0.92)
        self.assertEqual(log.items_json, [{'label': 'Pizza'}])
        self.assertEqual(log.processing_time_ms, 1500)

    def test_mark_failed(self):
        """Test marking a scan as failed."""
        log = ScanLog.objects.create(
            user=self.user,
            status=ScanLog.STATUS_PENDING
        )

        log.mark_failed(
            error_code='API_ERROR',
            processing_time_ms=500
        )

        log.refresh_from_db()
        self.assertEqual(log.status, ScanLog.STATUS_FAILED)
        self.assertEqual(log.error_code, 'API_ERROR')
        self.assertEqual(log.processing_time_ms, 500)

    def test_mark_timeout(self):
        """Test marking a scan as timed out."""
        log = ScanLog.objects.create(
            user=self.user,
            status=ScanLog.STATUS_PENDING
        )

        log.mark_timeout(processing_time_ms=30000)

        log.refresh_from_db()
        self.assertEqual(log.status, ScanLog.STATUS_TIMEOUT)
        self.assertEqual(log.error_code, 'TIMEOUT')
        self.assertEqual(log.processing_time_ms, 30000)

    def test_record_action(self):
        """Test recording an action."""
        log = ScanLog.objects.create(
            user=self.user,
            status=ScanLog.STATUS_SUCCESS,
            category='food'
        )

        log.record_action('log_food')

        log.refresh_from_db()
        self.assertEqual(log.action_taken, 'log_food')

    def test_str_representation(self):
        """Test string representation."""
        log = ScanLog.objects.create(
            user=self.user,
            category='medicine'
        )

        self.assertIn('medicine', str(log))
        self.assertIn(str(log.request_id), str(log))

    def test_ordering(self):
        """Test that logs are ordered by created_at descending."""
        log1 = ScanLog.objects.create(user=self.user, category='food')
        log2 = ScanLog.objects.create(user=self.user, category='medicine')
        log3 = ScanLog.objects.create(user=self.user, category='document')

        logs = list(ScanLog.objects.all())

        # Most recent first
        self.assertEqual(logs[0], log3)
        self.assertEqual(logs[1], log2)
        self.assertEqual(logs[2], log1)


class ScanConsentModelTests(ScanTestMixin, TestCase):
    """Tests for the ScanConsent model."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_consent(self):
        """Test creating a consent record."""
        consent = ScanConsent.objects.create(
            user=self.user,
            consent_version='1.0'
        )

        self.assertEqual(consent.user, self.user)
        self.assertEqual(consent.consent_version, '1.0')
        self.assertIsNotNone(consent.consented_at)

    def test_one_consent_per_user(self):
        """Test that only one consent per user is allowed."""
        ScanConsent.objects.create(
            user=self.user,
            consent_version='1.0'
        )

        # Attempting to create another should raise IntegrityError
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            ScanConsent.objects.create(
                user=self.user,
                consent_version='1.1'
            )

    def test_str_representation(self):
        """Test string representation."""
        consent = ScanConsent.objects.create(
            user=self.user,
            consent_version='1.0'
        )

        self.assertIn(self.user.email, str(consent))
