"""Integration tests for capture upload -> process -> display flow."""

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.capture.models import CaptureEntry

User = get_user_model()


# Use simpler static files storage to avoid manifest issues in tests
STATICFILES_OVERRIDE = {
    'STATICFILES_STORAGE': 'django.contrib.staticfiles.storage.StaticFilesStorage'
}


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class CaptureUploadToProcessFlowTests(TestCase):
    """
    Integration tests for the complete capture flow:
    Upload -> Transcription -> Summarization -> Ready
    """

    def setUp(self):
        """Set up test user and client."""
        self.client = Client()
        self.user = self._create_user()
        self.client.login(email='testuser@example.com', password='testpass123')

    def _create_user(self, email='testuser@example.com', password='testpass123'):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        return user

    def _accept_terms(self, user):
        """Accept terms of service for user."""
        try:
            from apps.users.models import TermsAcceptance
            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
            )
        except (ImportError, Exception):
            pass

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def test_complete_upload_flow_via_file_upload(self):
        """Test complete flow: file upload creates entry and triggers processing."""
        # Step 1: Upload a file
        fake_file = SimpleUploadedFile(
            'test_recording.mp3',
            b'fake audio content',
            content_type='audio/mpeg'
        )
        response = self.client.post(
            reverse('capture:upload'),
            {'file': fake_file}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        entry_id = data.get('entry_id')
        self.assertIsNotNone(entry_id)

        # Step 2: Verify entry was created with correct initial state
        entry = CaptureEntry.objects.get(pk=entry_id)
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.title, 'test_recording')

    def test_complete_submit_flow_via_presigned_url(self):
        """Test complete flow: get presigned URL -> confirm upload -> process.

        Note: When S3 is not configured, the system uses mock mode which
        creates entries directly in READY status. This test verifies both paths.
        """
        # Step 1: Request upload URL
        response = self.client.post(
            reverse('capture:submit'),
            data=json.dumps({
                'action': 'get_upload_url',
                'content_type': 'audio/webm',
                'title': 'My Recording',
                'duration_seconds': 120
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        entry_id = data.get('entry_id')
        self.assertIsNotNone(entry_id)

        # Get the entry
        entry = CaptureEntry.objects.get(pk=entry_id)
        self.assertEqual(entry.title, 'My Recording')
        self.assertEqual(entry.duration_seconds, 120)

        # Check if we're in mock mode (S3 not configured)
        if data.get('mock_mode'):
            # In mock mode, entry goes directly to READY status
            self.assertEqual(entry.status, CaptureEntry.STATUS_READY)
            # No confirm step needed in mock mode
        else:
            # Real S3 mode - verify uploading state
            self.assertEqual(entry.status, CaptureEntry.STATUS_UPLOADING)

            # Step 2: Confirm upload (simulates S3 upload complete)
            response = self.client.post(
                reverse('capture:submit'),
                data=json.dumps({
                    'action': 'confirm_upload',
                    'entry_id': str(entry_id)
                }),
                content_type='application/json'
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data.get('success'))
            self.assertEqual(data.get('status'), CaptureEntry.STATUS_TRANSCRIBING)

            # Verify entry is now transcribing
            entry.refresh_from_db()
            self.assertEqual(entry.status, CaptureEntry.STATUS_TRANSCRIBING)

    def test_full_processing_pipeline_simulation(self):
        """Test simulated full processing pipeline by updating entry states."""
        # Create entry in transcribing state (simulating post-upload)
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Recording',
            status=CaptureEntry.STATUS_TRANSCRIBING,
            audio_file_url='https://s3.example.com/audio.webm'
        )

        # Simulate transcription completing
        entry.transcript = 'This is the transcribed text from the recording.'
        entry.status = CaptureEntry.STATUS_SUMMARIZING
        entry.save()

        entry.refresh_from_db()
        self.assertEqual(entry.status, CaptureEntry.STATUS_SUMMARIZING)
        self.assertIn('transcribed text', entry.transcript)

        # Simulate summarization completing
        entry.summary = 'Key points: transcribed text from recording.'
        entry.category = CaptureEntry.CATEGORY_ORGANIZE
        entry.subcategory = CaptureEntry.SUBCATEGORY_NOTES
        entry.status = CaptureEntry.STATUS_READY
        entry.save()

        entry.refresh_from_db()
        self.assertEqual(entry.status, CaptureEntry.STATUS_READY)
        self.assertIn('Key points', entry.summary)
        self.assertEqual(entry.category, CaptureEntry.CATEGORY_ORGANIZE)

    def test_status_polling_during_processing(self):
        """Test status polling returns correct states during processing."""
        # Create entry in different states and verify status API
        states_to_test = [
            (CaptureEntry.STATUS_UPLOADING, 25, 'Uploading'),
            (CaptureEntry.STATUS_TRANSCRIBING, 50, 'Transcribing'),
            (CaptureEntry.STATUS_SUMMARIZING, 75, 'Summarizing'),
            (CaptureEntry.STATUS_READY, 100, 'Ready'),
        ]

        for status, expected_progress, expected_message in states_to_test:
            entry = CaptureEntry.objects.create(
                user=self.user,
                title=f'Entry {status}',
                status=status
            )

            response = self.client.get(
                reverse('capture:status', kwargs={'entry_id': entry.id})
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data.get('status'), status)
            self.assertEqual(data.get('progress'), expected_progress)
            self.assertEqual(data.get('status_message'), expected_message)

    def test_ready_entry_appears_in_list(self):
        """Test that ready entries appear in the list view."""
        # Create a ready entry
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Ready Recording',
            status=CaptureEntry.STATUS_READY,
            summary='This is the summary',
            transcript='This is the transcript'
        )

        # Check list view
        response = self.client.get(reverse('capture:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ready Recording')
        self.assertContains(response, 'Ready')

    def test_ready_entry_detail_shows_all_content(self):
        """Test that ready entry detail view shows all content."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Complete Recording',
            status=CaptureEntry.STATUS_READY,
            summary='BLUF: This is the summary content.',
            transcript='Full transcript of the recording here.',
            category=CaptureEntry.CATEGORY_FAITH,
            subcategory=CaptureEntry.SUBCATEGORY_SERMON,
            duration_seconds=185,
            audio_file_url='https://s3.example.com/audio.mp3'
        )

        response = self.client.get(
            reverse('capture:detail', kwargs={'pk': entry.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Complete Recording')
        self.assertContains(response, 'This is the summary content')
        self.assertContains(response, 'Full transcript')
        self.assertContains(response, 'Faith')
        self.assertContains(response, 'Sermon')
        self.assertContains(response, '3:05')  # Formatted duration


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class CaptureFailureFlowTests(TestCase):
    """Integration tests for failure handling in capture flow."""

    def setUp(self):
        """Set up test user and client."""
        self.client = Client()
        self.user = self._create_user()
        self.client.login(email='testuser@example.com', password='testpass123')

    def _create_user(self, email='testuser@example.com', password='testpass123'):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        return user

    def _accept_terms(self, user):
        """Accept terms of service for user."""
        try:
            from apps.users.models import TermsAcceptance
            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
            )
        except (ImportError, Exception):
            pass

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def test_failed_entry_shows_error_in_status(self):
        """Test that failed entry shows error message in status API."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Failed Recording',
            status=CaptureEntry.STATUS_FAILED,
            error_message='Transcription failed: audio quality too poor'
        )

        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': entry.id})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), CaptureEntry.STATUS_FAILED)
        self.assertEqual(data.get('progress'), 0)
        self.assertIn('audio quality', data.get('error_message', ''))

    def test_failed_entry_shows_error_in_detail(self):
        """Test that failed entry shows error in detail view."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Failed Recording',
            status=CaptureEntry.STATUS_FAILED,
            error_message='Summarization service unavailable'
        )

        response = self.client.get(
            reverse('capture:detail', kwargs={'pk': entry.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Processing Failed')
        self.assertContains(response, 'Summarization service unavailable')

    def test_failed_entry_can_be_deleted(self):
        """Test that failed entries can be deleted."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Failed Recording',
            status=CaptureEntry.STATUS_FAILED,
            error_message='Some error'
        )
        entry_id = entry.pk

        response = self.client.post(
            reverse('capture:delete', kwargs={'pk': entry.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CaptureEntry.objects.filter(pk=entry_id).exists())


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class CaptureAudioExpirationFlowTests(TestCase):
    """Integration tests for audio expiration flow."""

    def setUp(self):
        """Set up test user and client."""
        self.client = Client()
        self.user = self._create_user()
        self.client.login(email='testuser@example.com', password='testpass123')

    def _create_user(self, email='testuser@example.com', password='testpass123'):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        return user

    def _accept_terms(self, user):
        """Accept terms of service for user."""
        try:
            from apps.users.models import TermsAcceptance
            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
            )
        except (ImportError, Exception):
            pass

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def test_entry_with_active_audio_shows_player(self):
        """Test entry with active audio shows audio player."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Active Audio',
            status=CaptureEntry.STATUS_READY,
            audio_file_url='https://s3.example.com/audio.mp3',
            audio_expires_at=timezone.now() + timedelta(days=5)
        )

        response = self.client.get(
            reverse('capture:detail', kwargs={'pk': entry.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Audio Recording')
        self.assertContains(response, 'Download Audio')

    def test_entry_with_expired_audio_shows_message(self):
        """Test entry with expired audio shows expiration message."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Expired Audio',
            status=CaptureEntry.STATUS_READY,
            audio_file_url='',  # Empty URL = expired
            summary='The summary is still available',
            transcript='The transcript is still available'
        )

        response = self.client.get(
            reverse('capture:detail', kwargs={'pk': entry.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Audio no longer available')
        self.assertContains(response, 'The summary is still available')
        self.assertContains(response, 'The transcript is still available')
        self.assertNotContains(response, 'Download Audio')

    def test_list_shows_expired_indicator(self):
        """Test list view shows expired indicator for expired audio."""
        from django.utils import timezone
        from datetime import timedelta

        # Create one active and one expired entry
        CaptureEntry.objects.create(
            user=self.user,
            title='Active Entry',
            status=CaptureEntry.STATUS_READY,
            audio_file_url='https://s3.example.com/audio.mp3',
            audio_expires_at=timezone.now() + timedelta(days=7)
        )
        CaptureEntry.objects.create(
            user=self.user,
            title='Expired Entry',
            status=CaptureEntry.STATUS_READY,
            audio_file_url='',
            audio_expires_at=timezone.now() - timedelta(days=1)  # Expired yesterday
        )

        response = self.client.get(reverse('capture:list'))
        self.assertEqual(response.status_code, 200)
        # Should show "Audio expired" for one entry
        self.assertContains(response, 'Audio expired')


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class CaptureMultiUserIsolationTests(TestCase):
    """Integration tests for user isolation in capture feature."""

    def setUp(self):
        """Set up test users and clients."""
        self.client1 = Client()
        self.client2 = Client()

        self.user1 = self._create_user('user1@example.com')
        self.user2 = self._create_user('user2@example.com')

        self.client1.login(email='user1@example.com', password='testpass123')
        self.client2.login(email='user2@example.com', password='testpass123')

    def _create_user(self, email, password='testpass123'):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        return user

    def _accept_terms(self, user):
        """Accept terms of service for user."""
        try:
            from apps.users.models import TermsAcceptance
            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
            )
        except (ImportError, Exception):
            pass

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def test_user_only_sees_own_entries_in_list(self):
        """Test that users only see their own entries in list view."""
        CaptureEntry.objects.create(
            user=self.user1,
            title='User 1 Recording',
            status=CaptureEntry.STATUS_READY
        )
        CaptureEntry.objects.create(
            user=self.user2,
            title='User 2 Recording',
            status=CaptureEntry.STATUS_READY
        )

        # User 1 sees only their entry
        response1 = self.client1.get(reverse('capture:list'))
        self.assertContains(response1, 'User 1 Recording')
        self.assertNotContains(response1, 'User 2 Recording')

        # User 2 sees only their entry
        response2 = self.client2.get(reverse('capture:list'))
        self.assertContains(response2, 'User 2 Recording')
        self.assertNotContains(response2, 'User 1 Recording')

    def test_user_cannot_access_other_users_detail(self):
        """Test that users cannot access other users' entry details."""
        entry = CaptureEntry.objects.create(
            user=self.user1,
            title='User 1 Recording',
            status=CaptureEntry.STATUS_READY
        )

        # User 2 cannot access User 1's entry
        response = self.client2.get(
            reverse('capture:detail', kwargs={'pk': entry.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_user_cannot_delete_other_users_entry(self):
        """Test that users cannot delete other users' entries."""
        entry = CaptureEntry.objects.create(
            user=self.user1,
            title='User 1 Recording',
            status=CaptureEntry.STATUS_READY
        )

        # User 2 cannot delete User 1's entry
        response = self.client2.post(
            reverse('capture:delete', kwargs={'pk': entry.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 404)

        # Entry still exists
        self.assertTrue(CaptureEntry.objects.filter(pk=entry.pk).exists())

    def test_user_cannot_update_other_users_title(self):
        """Test that users cannot update other users' entry titles."""
        entry = CaptureEntry.objects.create(
            user=self.user1,
            title='Original Title',
            status=CaptureEntry.STATUS_READY
        )

        # User 2 cannot update User 1's entry
        response = self.client2.post(
            reverse('capture:update_title', kwargs={'pk': entry.pk}),
            data=json.dumps({'title': 'Hacked Title'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

        # Title unchanged
        entry.refresh_from_db()
        self.assertEqual(entry.title, 'Original Title')

    def test_user_cannot_poll_other_users_status(self):
        """Test that users cannot poll other users' entry status."""
        entry = CaptureEntry.objects.create(
            user=self.user1,
            title='User 1 Recording',
            status=CaptureEntry.STATUS_TRANSCRIBING
        )

        # User 2 cannot poll User 1's entry status
        response = self.client2.get(
            reverse('capture:status', kwargs={'entry_id': entry.id})
        )
        self.assertEqual(response.status_code, 404)


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class CaptureProcessingSimulationTests(TestCase):
    """Integration tests simulating the async processing pipeline."""

    def setUp(self):
        """Set up test user and client."""
        self.client = Client()
        self.user = self._create_user()
        self.client.login(email='testuser@example.com', password='testpass123')

    def _create_user(self, email='testuser@example.com', password='testpass123'):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        return user

    def _accept_terms(self, user):
        """Accept terms of service for user."""
        try:
            from apps.users.models import TermsAcceptance
            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
            )
        except (ImportError, Exception):
            pass

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def test_simulated_transcription_updates_entry(self):
        """Test that transcription service updates entry correctly."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Recording',
            status=CaptureEntry.STATUS_TRANSCRIBING,
            audio_file_url='https://s3.example.com/audio.webm'
        )

        # Simulate transcription service updating entry
        entry.transcript = 'This is the transcribed content.'
        entry.status = CaptureEntry.STATUS_SUMMARIZING
        entry.save()

        # Verify through status API
        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': entry.id})
        )
        data = response.json()
        self.assertEqual(data.get('status'), CaptureEntry.STATUS_SUMMARIZING)
        self.assertEqual(data.get('progress'), 75)

    def test_simulated_summarization_updates_entry(self):
        """Test that summarization service updates entry correctly."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Recording',
            status=CaptureEntry.STATUS_SUMMARIZING,
            transcript='This is the transcript content.'
        )

        # Simulate summarization service updating entry
        entry.summary = 'BLUF: Key summary points here.'
        entry.category = CaptureEntry.CATEGORY_FAITH
        entry.subcategory = CaptureEntry.SUBCATEGORY_SERMON
        entry.status = CaptureEntry.STATUS_READY
        entry.save()

        # Verify through status API
        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': entry.id})
        )
        data = response.json()
        self.assertEqual(data.get('status'), CaptureEntry.STATUS_READY)
        self.assertEqual(data.get('progress'), 100)
        self.assertIn('redirect_url', data)

        # Verify through detail view
        response = self.client.get(
            reverse('capture:detail', kwargs={'pk': entry.pk})
        )
        self.assertContains(response, 'Key summary points')
        self.assertContains(response, 'Faith')
        self.assertContains(response, 'Sermon')

    def test_simulated_failure_during_transcription(self):
        """Test that transcription failure updates entry correctly."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Recording',
            status=CaptureEntry.STATUS_TRANSCRIBING,
            audio_file_url='https://s3.example.com/audio.webm'
        )

        # Simulate transcription failure
        entry.status = CaptureEntry.STATUS_FAILED
        entry.error_message = 'OpenAI API error: rate limit exceeded'
        entry.save()

        # Verify through status API
        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': entry.id})
        )
        data = response.json()
        self.assertEqual(data.get('status'), CaptureEntry.STATUS_FAILED)
        self.assertEqual(data.get('progress'), 0)
        self.assertIn('rate limit', data.get('error_message', ''))

    def test_simulated_failure_during_summarization(self):
        """Test that summarization failure updates entry correctly."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Recording',
            status=CaptureEntry.STATUS_SUMMARIZING,
            transcript='Valid transcript content'
        )

        # Simulate summarization failure
        entry.status = CaptureEntry.STATUS_FAILED
        entry.error_message = 'Summarization service timeout'
        entry.save()

        # Verify through detail view
        response = self.client.get(
            reverse('capture:detail', kwargs={'pk': entry.pk})
        )
        self.assertContains(response, 'Processing Failed')
        self.assertContains(response, 'Summarization service timeout')
