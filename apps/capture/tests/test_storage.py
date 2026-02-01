"""Tests for capture storage utilities."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.capture.storage import (
    CaptureStorageNotConfiguredError,
    _get_extension_from_content_type,
    is_storage_configured,
)


class ExtensionFromContentTypeTests(TestCase):
    """Tests for _get_extension_from_content_type function."""

    def test_webm_content_type(self):
        """Test audio/webm returns webm extension."""
        self.assertEqual(_get_extension_from_content_type('audio/webm'), 'webm')

    def test_mp3_content_type(self):
        """Test audio/mp3 returns mp3 extension."""
        self.assertEqual(_get_extension_from_content_type('audio/mp3'), 'mp3')

    def test_mpeg_content_type(self):
        """Test audio/mpeg returns mp3 extension."""
        self.assertEqual(_get_extension_from_content_type('audio/mpeg'), 'mp3')

    def test_wav_content_type(self):
        """Test audio/wav returns wav extension."""
        self.assertEqual(_get_extension_from_content_type('audio/wav'), 'wav')

    def test_m4a_content_type(self):
        """Test audio/mp4 returns m4a extension."""
        self.assertEqual(_get_extension_from_content_type('audio/mp4'), 'm4a')

    def test_unknown_content_type(self):
        """Test unknown content type returns webm as default."""
        self.assertEqual(_get_extension_from_content_type('audio/unknown'), 'webm')


class IsStorageConfiguredTests(TestCase):
    """Tests for is_storage_configured function."""

    @override_settings(
        CAPTURE_AUDIO_BUCKET='test-bucket',
        CAPTURE_AWS_ACCESS_KEY_ID='test-key',
        CAPTURE_AWS_SECRET_ACCESS_KEY='test-secret',
    )
    def test_storage_configured(self):
        """Test returns True when all settings are present."""
        self.assertTrue(is_storage_configured())

    @override_settings(
        CAPTURE_AUDIO_BUCKET='',
        CAPTURE_AWS_ACCESS_KEY_ID='test-key',
        CAPTURE_AWS_SECRET_ACCESS_KEY='test-secret',
    )
    def test_storage_not_configured_no_bucket(self):
        """Test returns False when bucket is missing."""
        self.assertFalse(is_storage_configured())

    @override_settings(
        CAPTURE_AUDIO_BUCKET='test-bucket',
        CAPTURE_AWS_ACCESS_KEY_ID='',
        CAPTURE_AWS_SECRET_ACCESS_KEY='test-secret',
    )
    def test_storage_not_configured_no_access_key(self):
        """Test returns False when access key is missing."""
        self.assertFalse(is_storage_configured())

    @override_settings(
        CAPTURE_AUDIO_BUCKET='test-bucket',
        CAPTURE_AWS_ACCESS_KEY_ID='test-key',
        CAPTURE_AWS_SECRET_ACCESS_KEY='',
    )
    def test_storage_not_configured_no_secret_key(self):
        """Test returns False when secret key is missing."""
        self.assertFalse(is_storage_configured())


@override_settings(
    CAPTURE_AUDIO_BUCKET='test-bucket',
    CAPTURE_AWS_ACCESS_KEY_ID='test-key',
    CAPTURE_AWS_SECRET_ACCESS_KEY='test-secret',
    CAPTURE_AWS_REGION='us-east-1',
    CAPTURE_S3_ENDPOINT_URL='',
    CAPTURE_AUDIO_RETENTION_DAYS=7,
    CAPTURE_PRESIGNED_URL_EXPIRATION=3600,
)
class GenerateUploadPresignedUrlTests(TestCase):
    """Tests for generate_upload_presigned_url function."""

    def setUp(self):
        """Set up mock boto3."""
        # Create mock boto3 module
        self.mock_boto3 = MagicMock()
        self.mock_client = MagicMock()
        self.mock_boto3.client.return_value = self.mock_client

        # Patch boto3 in sys.modules before importing the function
        self.boto3_patcher = patch.dict('sys.modules', {'boto3': self.mock_boto3})
        self.botocore_config = MagicMock()
        self.botocore_patcher = patch.dict('sys.modules', {
            'botocore': MagicMock(),
            'botocore.config': self.botocore_config,
        })
        self.boto3_patcher.start()
        self.botocore_patcher.start()

    def tearDown(self):
        """Clean up patches."""
        self.boto3_patcher.stop()
        self.botocore_patcher.stop()

    def test_generate_upload_url_success(self):
        """Test successful upload URL generation."""
        self.mock_client.generate_presigned_url.return_value = 'https://s3.example.com/upload-url'

        # Import after patching
        from apps.capture.storage import generate_upload_presigned_url

        result = generate_upload_presigned_url(
            user_id='user-123',
            content_type='audio/webm',
        )

        self.assertIn('url', result)
        self.assertIn('key', result)
        self.assertIn('expires_at', result)
        self.assertIn('audio_expires_at', result)
        self.assertEqual(result['url'], 'https://s3.example.com/upload-url')
        self.assertIn('captures/user-123/', result['key'])
        self.assertIn('.webm', result['key'])

    def test_upload_url_key_format(self):
        """Test that the S3 key has correct format."""
        self.mock_client.generate_presigned_url.return_value = 'https://s3.example.com/upload-url'

        from apps.capture.storage import generate_upload_presigned_url

        result = generate_upload_presigned_url(
            user_id='user-456',
            content_type='audio/mp3',
        )

        # Key should be captures/{user_id}/{uuid}.{ext}
        self.assertTrue(result['key'].startswith('captures/user-456/'))
        self.assertTrue(result['key'].endswith('.mp3'))

    def test_upload_url_with_filename(self):
        """Test that filename extension is used when provided."""
        self.mock_client.generate_presigned_url.return_value = 'https://s3.example.com/upload-url'

        from apps.capture.storage import generate_upload_presigned_url

        result = generate_upload_presigned_url(
            user_id='user-789',
            content_type='audio/webm',
            filename='my-recording.ogg',
        )

        # Should use extension from filename, not content_type
        self.assertTrue(result['key'].endswith('.ogg'))

    def test_upload_url_expiration_times(self):
        """Test that expiration times are correctly calculated."""
        self.mock_client.generate_presigned_url.return_value = 'https://s3.example.com/upload-url'

        from apps.capture.storage import generate_upload_presigned_url

        before = timezone.now()
        result = generate_upload_presigned_url(user_id='user-123')
        after = timezone.now()

        # URL expires in ~1 hour
        expected_url_expiry = before + timedelta(seconds=3600)
        self.assertGreaterEqual(result['expires_at'], expected_url_expiry - timedelta(seconds=5))
        self.assertLessEqual(result['expires_at'], after + timedelta(seconds=3600))

        # Audio expires in ~7 days
        expected_audio_expiry = before + timedelta(days=7)
        self.assertGreaterEqual(result['audio_expires_at'], expected_audio_expiry - timedelta(seconds=5))
        self.assertLessEqual(result['audio_expires_at'], after + timedelta(days=7))


@override_settings(
    CAPTURE_AUDIO_BUCKET='test-bucket',
    CAPTURE_AWS_ACCESS_KEY_ID='test-key',
    CAPTURE_AWS_SECRET_ACCESS_KEY='test-secret',
    CAPTURE_AWS_REGION='us-east-1',
    CAPTURE_S3_ENDPOINT_URL='',
    CAPTURE_PRESIGNED_URL_EXPIRATION=3600,
)
class GenerateDownloadPresignedUrlTests(TestCase):
    """Tests for generate_download_presigned_url function."""

    def setUp(self):
        """Set up mock boto3."""
        self.mock_boto3 = MagicMock()
        self.mock_client = MagicMock()
        self.mock_boto3.client.return_value = self.mock_client

        self.boto3_patcher = patch.dict('sys.modules', {'boto3': self.mock_boto3})
        self.botocore_patcher = patch.dict('sys.modules', {
            'botocore': MagicMock(),
            'botocore.config': MagicMock(),
        })
        self.boto3_patcher.start()
        self.botocore_patcher.start()

    def tearDown(self):
        """Clean up patches."""
        self.boto3_patcher.stop()
        self.botocore_patcher.stop()

    def test_generate_download_url_success(self):
        """Test successful download URL generation."""
        self.mock_client.generate_presigned_url.return_value = 'https://s3.example.com/download-url'

        from apps.capture.storage import generate_download_presigned_url

        result = generate_download_presigned_url(key='captures/user-123/file.webm')

        self.assertIn('url', result)
        self.assertIn('expires_at', result)
        self.assertEqual(result['url'], 'https://s3.example.com/download-url')

    def test_download_url_custom_expiration(self):
        """Test download URL with custom expiration."""
        self.mock_client.generate_presigned_url.return_value = 'https://s3.example.com/download-url'

        from apps.capture.storage import generate_download_presigned_url

        before = timezone.now()
        result = generate_download_presigned_url(
            key='captures/user-123/file.webm',
            expiration_seconds=7200,  # 2 hours
        )

        expected_expiry = before + timedelta(seconds=7200)
        self.assertGreaterEqual(result['expires_at'], expected_expiry - timedelta(seconds=5))


@override_settings(
    CAPTURE_AUDIO_BUCKET='',
    CAPTURE_AWS_ACCESS_KEY_ID='test-key',
    CAPTURE_AWS_SECRET_ACCESS_KEY='test-secret',
)
class StorageNotConfiguredTests(TestCase):
    """Tests for storage not configured errors."""

    def test_upload_raises_not_configured_no_bucket(self):
        """Test upload raises error when bucket not configured."""
        from apps.capture.storage import generate_upload_presigned_url

        with self.assertRaises(CaptureStorageNotConfiguredError) as context:
            generate_upload_presigned_url(user_id='user-123')

        self.assertIn('CAPTURE_AUDIO_BUCKET', str(context.exception))

    def test_download_raises_not_configured_no_bucket(self):
        """Test download raises error when bucket not configured."""
        from apps.capture.storage import generate_download_presigned_url

        with self.assertRaises(CaptureStorageNotConfiguredError) as context:
            generate_download_presigned_url(key='captures/user-123/file.webm')

        self.assertIn('CAPTURE_AUDIO_BUCKET', str(context.exception))


@override_settings(
    CAPTURE_AUDIO_BUCKET='test-bucket',
    CAPTURE_AWS_ACCESS_KEY_ID='',
    CAPTURE_AWS_SECRET_ACCESS_KEY='',
)
class StorageNoCredentialsTests(TestCase):
    """Tests for storage with missing credentials."""

    def test_upload_raises_not_configured_no_credentials(self):
        """Test upload raises error when credentials not configured."""
        from apps.capture.storage import generate_upload_presigned_url

        with self.assertRaises(CaptureStorageNotConfiguredError) as context:
            generate_upload_presigned_url(user_id='user-123')

        self.assertIn('credentials', str(context.exception).lower())
