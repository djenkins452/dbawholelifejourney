"""
Scan Views Tests - Comprehensive tests for scan views and security.

Tests cover:
- Authentication requirements
- Consent flows
- Rate limiting
- File validation
- API responses
"""

import base64
import json
import uuid
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

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
        self._enable_ai(user)
        return user

    def _accept_terms(self, user):
        TermsAcceptance.objects.create(user=user, terms_version='1.0')

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def _enable_ai(self, user):
        """Enable AI features and consent."""
        user.preferences.ai_enabled = True
        user.preferences.ai_data_consent = True
        user.preferences.save()

    def _grant_scan_consent(self, user):
        """Grant scan-specific consent."""
        ScanConsent.objects.create(user=user, consent_version='1.0')

    def get_valid_jpeg_base64(self):
        """Return a minimal valid JPEG image as base64."""
        # Minimal 1x1 white JPEG
        jpeg_bytes = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
            0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
            0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
            0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
            0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
            0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
            0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
            0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
            0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
            0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
            0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
            0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
            0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
            0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
            0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
            0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
            0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
            0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
            0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
            0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
            0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
            0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
            0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
            0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
            0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
            0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
            0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD5, 0xDB, 0x20, 0xB2, 0xF9, 0x6D, 0x60,
            0xF7, 0xFF, 0xD9
        ])
        return base64.b64encode(jpeg_bytes).decode('ascii')


class ScanHomeViewTests(ScanTestMixin, TestCase):
    """Tests for the scan home view."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.url = reverse('scan:home')

    def test_requires_authentication(self):
        """Test that unauthenticated users are redirected."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('accounts/login', response.url)

    def test_shows_ai_consent_prompt_if_not_enabled(self):
        """Test that users without AI consent see the enable AI prompt."""
        self.user.preferences.ai_enabled = False
        self.user.preferences.ai_data_consent = False
        self.user.preferences.save()

        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enable AI Features First')

    def test_shows_scan_consent_prompt_if_not_consented(self):
        """Test that users without scan consent see the consent form."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Before You Scan')

    def test_shows_camera_interface_when_consented(self):
        """Test that consented users see the camera interface."""
        self._grant_scan_consent(self.user)

        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'camera-preview')


class ScanConsentViewTests(ScanTestMixin, TestCase):
    """Tests for the scan consent view."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.url = reverse('scan:consent')

    def test_requires_authentication(self):
        """Test that unauthenticated users are redirected."""
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)

    def test_creates_consent_record(self):
        """Test that consent is recorded."""
        self.client.login(email='test@example.com', password='testpass123')

        self.assertFalse(ScanConsent.objects.filter(user=self.user).exists())

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ScanConsent.objects.filter(user=self.user).exists())


class ScanAnalyzeViewTests(ScanTestMixin, TestCase):
    """Tests for the scan analyze API endpoint."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self._grant_scan_consent(self.user)
        self.url = reverse('scan:analyze')
        cache.clear()  # Clear rate limit counters

    def test_requires_authentication(self):
        """Test that unauthenticated requests are rejected."""
        response = self.client.post(
            self.url,
            data=json.dumps({'image': 'test'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 302)

    def test_requires_ai_consent(self):
        """Test that users without AI consent are rejected."""
        self.user.preferences.ai_data_consent = False
        self.user.preferences.save()

        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.post(
            self.url,
            data=json.dumps({'image': 'test'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertEqual(data['error_code'], 'NO_CONSENT')

    def test_requires_scan_consent(self):
        """Test that users without scan consent are rejected."""
        ScanConsent.objects.filter(user=self.user).delete()

        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.post(
            self.url,
            data=json.dumps({'image': 'test'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertEqual(data['error_code'], 'NO_SCAN_CONSENT')

    def test_requires_image_data(self):
        """Test that requests without image are rejected."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.post(
            self.url,
            data=json.dumps({}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['error_code'], 'NO_IMAGE')

    def test_rejects_invalid_base64(self):
        """Test that invalid base64 is rejected."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.post(
            self.url,
            data=json.dumps({'image': 'not-valid-base64!!!'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['error_code'], 'INVALID_IMAGE')

    def test_rejects_non_image_file(self):
        """Test that non-image files are rejected."""
        # Create a text file disguised as base64
        text_data = base64.b64encode(b'This is not an image').decode('ascii')

        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.post(
            self.url,
            data=json.dumps({'image': text_data}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['error_code'], 'INVALID_IMAGE')
        self.assertIn('format', data['error'].lower())

    def test_rejects_oversized_image(self):
        """Test that oversized images are rejected via validate_image_data."""
        from apps.scan import views
        from apps.scan.views import validate_image_data

        # Temporarily lower the limit for this test
        original_limit = views.MAX_IMAGE_SIZE_BYTES
        views.MAX_IMAGE_SIZE_BYTES = 100 * 1024  # 100KB for testing

        try:
            # Create a 200KB image (larger than 100KB limit)
            large_data = base64.b64encode(b'\xFF\xD8\xFF' + b'x' * (200 * 1024)).decode('ascii')

            valid, error, data, fmt = validate_image_data(large_data)

            self.assertFalse(valid)
            self.assertIn('large', error.lower())
        finally:
            # Restore
            views.MAX_IMAGE_SIZE_BYTES = original_limit

    @override_settings(
        SCAN_RATE_LIMIT_PER_HOUR=2,
        CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
    )
    def test_rate_limiting(self):
        """Test that rate limiting is enforced."""
        from apps.scan import views
        from apps.scan.services import vision_service

        # Set module-level vars since settings override doesn't affect them
        views.RATE_LIMIT_PER_HOUR = 2
        cache.clear()

        self.client.login(email='test@example.com', password='testpass123')
        image_data = self.get_valid_jpeg_base64()

        # Make requests up to the limit - disable vision service
        original_client = vision_service.client
        vision_service.client = None

        try:
            for i in range(2):
                response = self.client.post(
                    self.url,
                    data=json.dumps({'image': image_data}),
                    content_type='application/json'
                )
                # These will return 503 because service is unavailable, but they count

            # Third request should be rate limited
            response = self.client.post(
                self.url,
                data=json.dumps({'image': image_data}),
                content_type='application/json'
            )

            self.assertEqual(response.status_code, 429)
            data = response.json()
            self.assertEqual(data['error_code'], 'RATE_LIMITED')
            self.assertIn('Retry-After', response.headers)
        finally:
            # Restore
            vision_service.client = original_client
            views.RATE_LIMIT_PER_HOUR = 30

    @patch('apps.scan.views.vision_service')
    def test_successful_analysis(self, mock_vision_service):
        """Test successful image analysis."""
        from apps.scan.services.vision import ScanResult

        # Make service appear available
        mock_vision_service.is_available = True

        # The analyze_image function receives request_id from the view
        # and should return it in the result
        def mock_analyze(image_base64, request_id, image_format):
            return ScanResult(
                request_id=request_id,  # Use the same ID passed in
                top_category='food',
                confidence=0.92,
                items=[{'label': 'Pizza', 'details': {'type': 'margherita'}, 'confidence': 0.9}],
                safety_notes=[],
                next_best_actions=[]
            )

        mock_vision_service.analyze_image.side_effect = mock_analyze

        self.client.login(email='test@example.com', password='testpass123')
        image_data = self.get_valid_jpeg_base64()

        response = self.client.post(
            self.url,
            data=json.dumps({'image': image_data}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['top_category'], 'food')
        self.assertEqual(data['confidence'], 0.92)

        # Verify scan log was created
        scan_log = ScanLog.objects.get(request_id=data['request_id'])
        self.assertEqual(scan_log.user, self.user)
        self.assertEqual(scan_log.status, ScanLog.STATUS_SUCCESS)
        self.assertEqual(scan_log.category, 'food')

    def test_creates_scan_log(self):
        """Test that scan log is created for each request."""
        from apps.scan.services import vision_service

        self.client.login(email='test@example.com', password='testpass123')
        initial_count = ScanLog.objects.filter(user=self.user).count()

        # Disable vision service
        original_client = vision_service.client
        vision_service.client = None

        try:
            response = self.client.post(
                self.url,
                data=json.dumps({'image': self.get_valid_jpeg_base64()}),
                content_type='application/json'
            )

            # Log should be created even for failed requests
            self.assertEqual(
                ScanLog.objects.filter(user=self.user).count(),
                initial_count + 1
            )
        finally:
            vision_service.client = original_client


class ScanRecordActionViewTests(ScanTestMixin, TestCase):
    """Tests for the action recording view."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self._grant_scan_consent(self.user)

    def test_requires_authentication(self):
        """Test that unauthenticated requests are rejected."""
        request_id = str(uuid.uuid4())
        url = reverse('scan:record_action', kwargs={'request_id': request_id})
        response = self.client.post(url, {'action_id': 'skip'})
        self.assertEqual(response.status_code, 302)

    def test_returns_404_for_nonexistent_scan(self):
        """Test that 404 is returned for unknown scan."""
        self.client.login(email='test@example.com', password='testpass123')
        request_id = str(uuid.uuid4())
        url = reverse('scan:record_action', kwargs={'request_id': request_id})

        response = self.client.post(url, {'action_id': 'skip'})

        self.assertEqual(response.status_code, 404)

    def test_records_action(self):
        """Test that action is recorded."""
        scan_log = ScanLog.objects.create(
            user=self.user,
            request_id=uuid.uuid4(),
            status=ScanLog.STATUS_SUCCESS,
            category='food'
        )

        self.client.login(email='test@example.com', password='testpass123')
        url = reverse('scan:record_action', kwargs={'request_id': scan_log.request_id})

        response = self.client.post(url, {'action_id': 'log_food'})

        self.assertEqual(response.status_code, 200)

        scan_log.refresh_from_db()
        self.assertEqual(scan_log.action_taken, 'log_food')

    def test_cannot_record_action_for_other_users_scan(self):
        """Test that users can't record actions on other users' scans."""
        other_user = self.create_user(email='other@example.com')
        scan_log = ScanLog.objects.create(
            user=other_user,
            request_id=uuid.uuid4(),
            status=ScanLog.STATUS_SUCCESS
        )

        self.client.login(email='test@example.com', password='testpass123')
        url = reverse('scan:record_action', kwargs={'request_id': scan_log.request_id})

        response = self.client.post(url, {'action_id': 'skip'})

        self.assertEqual(response.status_code, 404)


class ScanHistoryViewTests(ScanTestMixin, TestCase):
    """Tests for the scan history view."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.url = reverse('scan:history')

    def test_requires_authentication(self):
        """Test that unauthenticated users are redirected."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_shows_user_scans_only(self):
        """Test that only the user's scans are shown."""
        # Create scan for this user
        ScanLog.objects.create(
            user=self.user,
            request_id=uuid.uuid4(),
            status=ScanLog.STATUS_SUCCESS,
            category='food'
        )

        # Create scan for another user
        other_user = self.create_user(email='other@example.com')
        ScanLog.objects.create(
            user=other_user,
            request_id=uuid.uuid4(),
            status=ScanLog.STATUS_SUCCESS,
            category='supplement'  # Using supplement instead of medicine (which appears in nav menu)
        )

        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Food')
        # Verify only 1 scan is shown by checking context
        self.assertEqual(len(response.context['scans']), 1)

    def test_shows_empty_state(self):
        """Test that empty state is shown when no scans."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No scans yet')


class BarcodeLookupViewTests(ScanTestMixin, TestCase):
    """Tests for the barcode lookup API endpoint."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self._grant_scan_consent(self.user)
        self.url = reverse('scan:barcode_lookup')
        cache.clear()

    def test_requires_authentication(self):
        """Test that unauthenticated requests are rejected."""
        response = self.client.post(
            self.url,
            data=json.dumps({'barcode': '012345678901'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 302)

    def test_requires_barcode(self):
        """Test that requests without barcode are rejected."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.post(
            self.url,
            data=json.dumps({}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['error_code'], 'NO_BARCODE')

    def test_barcode_not_found(self):
        """Test response when barcode is not in database."""
        self.client.login(email='test@example.com', password='testpass123')

        # Use a barcode that doesn't exist in database and mock AI to return not found
        with patch('apps.scan.services.barcode.BarcodeService._lookup_ai') as mock_ai:
            from apps.scan.services.barcode import BarcodeResult
            mock_ai.return_value = BarcodeResult(
                barcode='012345678901',
                found=False,
                source='not_found'
            )

            response = self.client.post(
                self.url,
                data=json.dumps({'barcode': '012345678901'}),
                content_type='application/json'
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertFalse(data['found'])
            self.assertEqual(data['barcode'], '012345678901')

    def test_barcode_found_in_database(self):
        """Test response when barcode is found in database."""
        from apps.health.models import FoodItem

        # Create a FoodItem with a barcode
        food_item = FoodItem.objects.create(
            name='Test Protein Bar',
            brand='Test Brand',
            barcode='012345678901',
            serving_size=40,
            serving_unit='g',
            calories=200,
            protein_g=20,
            carbohydrates_g=25,
            fat_g=8,
            fiber_g=3,
            sugar_g=5,
            saturated_fat_g=2,
            data_source=FoodItem.SOURCE_BARCODE
        )

        self.client.login(email='test@example.com', password='testpass123')

        response = self.client.post(
            self.url,
            data=json.dumps({'barcode': '012345678901'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['found'])
        self.assertEqual(data['source'], 'database')
        self.assertEqual(data['food_name'], 'Test Protein Bar')
        self.assertEqual(data['brand'], 'Test Brand')
        self.assertEqual(data['calories'], 200)
        self.assertEqual(data['protein_g'], 20)
        self.assertIn('food_entry_url', data)

        # Verify scan log was created
        scan_log = ScanLog.objects.filter(
            user=self.user,
            category='barcode'
        ).first()
        self.assertIsNotNone(scan_log)
        self.assertEqual(scan_log.status, ScanLog.STATUS_SUCCESS)

    @patch('apps.scan.services.barcode.BarcodeService._lookup_ai')
    def test_barcode_found_via_ai(self, mock_ai_lookup):
        """Test response when barcode is found via AI."""
        from apps.scan.services.barcode import BarcodeResult

        mock_ai_lookup.return_value = BarcodeResult(
            barcode='9876543210123',
            found=True,
            source='ai',
            food_name='AI Found Product',
            brand='AI Brand',
            calories=150,
            protein_g=10,
            carbohydrates_g=20,
            fat_g=5,
            fiber_g=2,
            sugar_g=8,
            saturated_fat_g=1,
            serving_size=30,
            serving_unit='g',
            confidence=0.85
        )

        self.client.login(email='test@example.com', password='testpass123')

        response = self.client.post(
            self.url,
            data=json.dumps({'barcode': '9876543210123'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['found'])
        self.assertEqual(data['source'], 'ai')
        self.assertEqual(data['food_name'], 'AI Found Product')

    def test_creates_scan_log_for_not_found(self):
        """Test that scan log is created even when barcode is not found."""
        self.client.login(email='test@example.com', password='testpass123')

        # Use a barcode that doesn't exist
        response = self.client.post(
            self.url,
            data=json.dumps({'barcode': '000000000000'}),
            content_type='application/json'
        )

        # Verify scan log was created
        scan_log = ScanLog.objects.filter(
            user=self.user,
            category='barcode'
        ).first()
        self.assertIsNotNone(scan_log)


class BarcodeServiceTests(TestCase):
    """Tests for the BarcodeService class."""

    def setUp(self):
        from apps.scan.services.barcode import BarcodeService
        self.service = BarcodeService()

    def test_clean_barcode_valid(self):
        """Test cleaning valid barcodes."""
        self.assertEqual(self.service._clean_barcode('012345678901'), '012345678901')
        self.assertEqual(self.service._clean_barcode('  012345678901  '), '012345678901')
        self.assertEqual(self.service._clean_barcode('0123456789012'), '0123456789012')

    def test_clean_barcode_invalid(self):
        """Test cleaning invalid barcodes."""
        self.assertEqual(self.service._clean_barcode(''), '')
        self.assertEqual(self.service._clean_barcode('123'), '')  # Too short
        self.assertEqual(self.service._clean_barcode('abc'), '')  # Not numeric

    def test_lookup_database_found(self):
        """Test database lookup when barcode exists."""
        from apps.health.models import FoodItem

        food_item = FoodItem.objects.create(
            name='Test Food',
            barcode='111111111111',
            serving_size=100,
            serving_unit='g',
            calories=100,
            protein_g=5,
            carbohydrates_g=10,
            fat_g=3
        )

        result = self.service._lookup_database('111111111111')

        self.assertIsNotNone(result)
        self.assertTrue(result.found)
        self.assertEqual(result.source, 'database')
        self.assertEqual(result.food_name, 'Test Food')
        self.assertEqual(result.food_item_id, food_item.id)

    def test_lookup_database_not_found(self):
        """Test database lookup when barcode doesn't exist."""
        result = self.service._lookup_database('999999999999')

        self.assertIsNone(result)

    def test_lookup_full_flow_database(self):
        """Test full lookup flow with database hit."""
        from apps.health.models import FoodItem

        FoodItem.objects.create(
            name='Database Product',
            barcode='222222222222',
            serving_size=50,
            serving_unit='g',
            calories=150,
            protein_g=8,
            carbohydrates_g=15,
            fat_g=6
        )

        result = self.service.lookup('222222222222', use_ai=False)

        self.assertTrue(result.found)
        self.assertEqual(result.source, 'database')
        self.assertEqual(result.food_name, 'Database Product')

    def test_lookup_no_ai_when_disabled(self):
        """Test that AI is not used when disabled."""
        result = self.service.lookup('333333333333', use_ai=False)

        self.assertFalse(result.found)
        self.assertEqual(result.source, 'not_found')

    def test_save_to_database(self):
        """Test saving AI result to database."""
        from apps.health.models import FoodItem
        from apps.scan.services.barcode import BarcodeResult

        result = BarcodeResult(
            barcode='444444444444',
            found=True,
            source='ai',
            food_name='AI Product',
            brand='AI Brand',
            calories=100,
            protein_g=5,
            carbohydrates_g=10,
            fat_g=3,
            serving_size=30,
            serving_unit='g',
            confidence=0.9
        )

        food_item_id = self.service.save_to_database(result)

        self.assertIsNotNone(food_item_id)

        food_item = FoodItem.objects.get(id=food_item_id)
        self.assertEqual(food_item.name, 'AI Product')
        self.assertEqual(food_item.barcode, '444444444444')
        self.assertEqual(food_item.data_source, FoodItem.SOURCE_BARCODE)
        self.assertFalse(food_item.is_verified)
