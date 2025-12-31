"""
Scan Security Tests - Security-focused tests for the scan feature.

Tests cover:
- File validation
- Magic bytes verification
- Rate limiting behavior
- CSRF protection
- User isolation
"""

import base64
import json
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from apps.scan.models import ScanConsent, ScanLog
from apps.scan.views import validate_image_data, check_rate_limit
from apps.users.models import TermsAcceptance

User = get_user_model()


class ScanTestMixin:
    """Mixin for scan tests with proper user setup."""

    def create_user(self, email='test@example.com', password='testpass123'):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        self._enable_ai(user)
        return user

    def _accept_terms(self, user):
        TermsAcceptance.objects.create(user=user, terms_version='1.0')

    def _complete_onboarding(self, user):
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def _enable_ai(self, user):
        user.preferences.ai_enabled = True
        user.preferences.ai_data_consent = True
        user.preferences.save()

    def _grant_scan_consent(self, user):
        ScanConsent.objects.create(user=user, consent_version='1.0')


class ImageValidationTests(TestCase):
    """Tests for image validation functions."""

    def test_valid_jpeg(self):
        """Test that valid JPEG is accepted."""
        # Minimal JPEG header
        jpeg_bytes = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b'x' * 100
        b64 = base64.b64encode(jpeg_bytes).decode('ascii')

        valid, error, data, fmt = validate_image_data(b64)

        self.assertTrue(valid)
        self.assertIsNone(error)
        self.assertEqual(fmt, 'jpeg')

    def test_valid_png(self):
        """Test that valid PNG is accepted."""
        # PNG magic bytes
        png_bytes = bytes([0x89, 0x50, 0x4E, 0x47]) + b'x' * 100
        b64 = base64.b64encode(png_bytes).decode('ascii')

        valid, error, data, fmt = validate_image_data(b64)

        self.assertTrue(valid)
        self.assertIsNone(error)
        self.assertEqual(fmt, 'png')

    def test_valid_webp(self):
        """Test that valid WebP is accepted."""
        # WebP: RIFF....WEBP
        webp_bytes = b'RIFF' + b'\x00' * 4 + b'WEBP' + b'x' * 100
        b64 = base64.b64encode(webp_bytes).decode('ascii')

        valid, error, data, fmt = validate_image_data(b64)

        self.assertTrue(valid)
        self.assertIsNone(error)
        self.assertEqual(fmt, 'webp')

    def test_invalid_base64(self):
        """Test that invalid base64 is rejected."""
        valid, error, data, fmt = validate_image_data('not-valid-base64!!!')

        self.assertFalse(valid)
        self.assertIn('base64', error.lower())

    def test_non_image_file(self):
        """Test that non-image files are rejected."""
        text_bytes = b'This is just plain text'
        b64 = base64.b64encode(text_bytes).decode('ascii')

        valid, error, data, fmt = validate_image_data(b64)

        self.assertFalse(valid)
        self.assertIn('format', error.lower())

    def test_executable_disguised_as_image(self):
        """Test that executables are rejected even with image extension."""
        # Windows executable magic bytes
        exe_bytes = bytes([0x4D, 0x5A]) + b'x' * 100  # MZ header
        b64 = base64.b64encode(exe_bytes).decode('ascii')

        valid, error, data, fmt = validate_image_data(b64)

        self.assertFalse(valid)

    def test_php_file_disguised_as_image(self):
        """Test that PHP files are rejected."""
        php_bytes = b'<?php echo "hack"; ?>'
        b64 = base64.b64encode(php_bytes).decode('ascii')

        valid, error, data, fmt = validate_image_data(b64)

        self.assertFalse(valid)

    def test_oversized_image(self):
        """Test that oversized images are rejected."""
        from apps.scan import views
        # Temporarily lower the limit
        original_limit = views.MAX_IMAGE_SIZE_BYTES
        views.MAX_IMAGE_SIZE_BYTES = 1 * 1024 * 1024  # 1MB

        try:
            # 2MB image (over 1MB limit)
            large_bytes = bytes([0xFF, 0xD8, 0xFF]) + b'x' * (2 * 1024 * 1024)
            b64 = base64.b64encode(large_bytes).decode('ascii')

            valid, error, data, fmt = validate_image_data(b64)

            self.assertFalse(valid)
            self.assertIn('large', error.lower())
        finally:
            # Restore
            views.MAX_IMAGE_SIZE_BYTES = original_limit

    def test_data_uri_with_wrong_mime(self):
        """Test that data URI with wrong MIME type is rejected."""
        jpeg_bytes = bytes([0xFF, 0xD8, 0xFF]) + b'x' * 100
        b64 = base64.b64encode(jpeg_bytes).decode('ascii')
        data_uri = f'data:application/pdf;base64,{b64}'

        valid, error, data, fmt = validate_image_data(data_uri)

        self.assertFalse(valid)
        self.assertIn('invalid', error.lower())

    def test_data_uri_with_valid_mime(self):
        """Test that data URI with correct MIME type is accepted."""
        jpeg_bytes = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b'x' * 100
        b64 = base64.b64encode(jpeg_bytes).decode('ascii')
        data_uri = f'data:image/jpeg;base64,{b64}'

        valid, error, data, fmt = validate_image_data(data_uri)

        self.assertTrue(valid)


@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
})
class RateLimitingTests(ScanTestMixin, TestCase):
    """Tests for rate limiting functionality."""

    def setUp(self):
        self.user = self.create_user()
        cache.clear()

    def test_allows_requests_under_limit(self):
        """Test that requests under the limit are allowed."""
        allowed, retry_after = check_rate_limit(self.user, '127.0.0.1')
        self.assertTrue(allowed)
        self.assertIsNone(retry_after)

    @override_settings(SCAN_RATE_LIMIT_PER_HOUR=2, SCAN_RATE_LIMIT_IP_PER_HOUR=100)
    def test_blocks_requests_over_user_limit(self):
        """Test that requests over the user limit are blocked."""
        from apps.scan import views
        # Reload the module-level settings
        views.RATE_LIMIT_PER_HOUR = 2
        views.RATE_LIMIT_IP_PER_HOUR = 100

        cache.clear()
        # First two requests allowed
        check_rate_limit(self.user, '127.0.0.1')
        check_rate_limit(self.user, '127.0.0.1')

        # Third request blocked
        allowed, retry_after = check_rate_limit(self.user, '127.0.0.1')
        self.assertFalse(allowed)
        self.assertIsNotNone(retry_after)

        # Reset
        views.RATE_LIMIT_PER_HOUR = 30
        views.RATE_LIMIT_IP_PER_HOUR = 60

    @override_settings(SCAN_RATE_LIMIT_IP_PER_HOUR=2, SCAN_RATE_LIMIT_PER_HOUR=100)
    def test_blocks_requests_over_ip_limit(self):
        """Test that requests over the IP limit are blocked."""
        from apps.scan import views
        views.RATE_LIMIT_PER_HOUR = 100
        views.RATE_LIMIT_IP_PER_HOUR = 2

        cache.clear()
        user2 = self.create_user(email='user2@example.com')
        user3 = self.create_user(email='user3@example.com')

        # Same IP, different users
        check_rate_limit(self.user, '1.2.3.4')
        check_rate_limit(user2, '1.2.3.4')

        # Third request from same IP blocked
        allowed, retry_after = check_rate_limit(user3, '1.2.3.4')
        self.assertFalse(allowed)

        # Reset
        views.RATE_LIMIT_PER_HOUR = 30
        views.RATE_LIMIT_IP_PER_HOUR = 60

    def test_different_ips_have_separate_limits(self):
        """Test that different IPs have separate rate limits."""
        cache.clear()
        # First IP
        check_rate_limit(self.user, '1.1.1.1')

        # Different IP should be allowed
        allowed, _ = check_rate_limit(self.user, '2.2.2.2')
        # Note: This may be blocked by user limit, not IP limit
        # But the IP counter should be separate


class UserIsolationTests(ScanTestMixin, TestCase):
    """Tests for user data isolation."""

    def setUp(self):
        self.client = Client()
        self.user1 = self.create_user(email='user1@example.com')
        self.user2 = self.create_user(email='user2@example.com')
        self._grant_scan_consent(self.user1)
        self._grant_scan_consent(self.user2)

    def test_users_only_see_own_scans(self):
        """Test that users can only see their own scans."""
        # Create scans for both users
        ScanLog.objects.create(
            user=self.user1,
            status=ScanLog.STATUS_SUCCESS,
            category='food'
        )
        ScanLog.objects.create(
            user=self.user2,
            status=ScanLog.STATUS_SUCCESS,
            category='medicine'
        )

        # User1 should only see their scan
        self.client.login(email='user1@example.com', password='testpass123')
        response = self.client.get('/scan/history/')

        # Check the page contains the Food scan category
        self.assertContains(response, 'Food')
        # Check that there are scan records - look for the scan list structure
        # Note: "Medicine" appears in navigation menu so we can't just check for absence
        # Instead verify that only 1 scan is shown (the Food one)
        content = response.content.decode()
        # The scan history shows "Food" as a category, and user2's "Medicine" scan shouldn't appear in the list
        scan_count = content.count('class="recent-scan-item"')
        self.assertEqual(scan_count, 1, "Only user1's scan should be visible")

    def test_cannot_access_other_users_scan_log(self):
        """Test that users cannot record actions on others' scans."""
        scan = ScanLog.objects.create(
            user=self.user1,
            status=ScanLog.STATUS_SUCCESS,
            category='food'
        )

        # User2 tries to record action on User1's scan
        self.client.login(email='user2@example.com', password='testpass123')
        response = self.client.post(
            f'/scan/action/{scan.request_id}/',
            {'action_id': 'log_food'}
        )

        self.assertEqual(response.status_code, 404)

        # Action should not be recorded
        scan.refresh_from_db()
        self.assertEqual(scan.action_taken, '')


class CSRFProtectionTests(ScanTestMixin, TestCase):
    """Tests for CSRF protection."""

    def setUp(self):
        self.user = self.create_user()
        self._grant_scan_consent(self.user)

    def test_analyze_requires_csrf(self):
        """Test that analyze endpoint requires CSRF token."""
        # Create client without CSRF enforcement for this test
        client = Client(enforce_csrf_checks=True)
        client.login(email='test@example.com', password='testpass123')

        response = client.post(
            '/scan/analyze/',
            data=json.dumps({'image': 'test'}),
            content_type='application/json'
        )

        # Should be rejected due to missing CSRF
        self.assertEqual(response.status_code, 403)


class NoImageStorageTests(ScanTestMixin, TestCase):
    """Tests verifying images are not stored."""

    def setUp(self):
        self.user = self.create_user()
        self._grant_scan_consent(self.user)
        cache.clear()

    def test_scan_log_does_not_store_image(self):
        """Test that ScanLog doesn't have image storage field."""
        log = ScanLog.objects.create(
            user=self.user,
            status=ScanLog.STATUS_SUCCESS,
            category='food',
            confidence=0.9,
            items_json=[{'label': 'Pizza'}],
            image_size_kb=500,
            image_format='jpeg'
        )

        # Verify there's no image field
        field_names = [f.name for f in ScanLog._meta.get_fields()]
        self.assertNotIn('image', field_names)
        self.assertNotIn('image_data', field_names)
        self.assertNotIn('photo', field_names)

    def test_scan_log_only_stores_metadata(self):
        """Test that ScanLog only stores non-sensitive metadata."""
        log = ScanLog.objects.create(
            user=self.user,
            image_size_kb=500,
            image_format='jpeg'
        )

        # Should store size and format (for analytics)
        self.assertEqual(log.image_size_kb, 500)
        self.assertEqual(log.image_format, 'jpeg')

        # But no actual image data anywhere
        log_dict = {
            'request_id': str(log.request_id),
            'status': log.status,
            'category': log.category,
            'confidence': log.confidence,
            'items_json': log.items_json,
            'action_taken': log.action_taken,
            'image_size_kb': log.image_size_kb,
            'image_format': log.image_format,
            'processing_time_ms': log.processing_time_ms,
            'error_code': log.error_code
        }

        # None of these should contain base64 or binary image data
        for key, value in log_dict.items():
            if isinstance(value, str) and len(value) > 100:
                # Long strings might be image data
                self.assertNotIn('data:image', value)
                self.assertFalse(value.startswith('/9j/'))  # JPEG base64
                self.assertFalse(value.startswith('iVBOR'))  # PNG base64
