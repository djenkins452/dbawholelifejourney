"""Tests for capture views."""

import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.capture.models import CaptureEntry

User = get_user_model()


class CaptureListViewTests(TestCase):
    """Tests for CaptureListView."""

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

    def test_list_view_requires_login(self):
        """List view requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('capture:list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_list_view_loads(self):
        """List view loads for authenticated user."""
        response = self.client.get(reverse('capture:list'))
        self.assertEqual(response.status_code, 200)

    def test_list_view_uses_correct_template(self):
        """List view uses the correct template."""
        response = self.client.get(reverse('capture:list'))
        self.assertTemplateUsed(response, 'capture/capture_list.html')

    def test_list_view_empty_state(self):
        """List view shows empty state when no entries exist."""
        response = self.client.get(reverse('capture:list'))
        self.assertContains(response, 'No recordings yet')

    def test_list_view_shows_user_entries(self):
        """List view shows the user's entries."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='My Recording',
            status=CaptureEntry.STATUS_READY,
        )
        response = self.client.get(reverse('capture:list'))
        self.assertContains(response, 'My Recording')

    def test_list_view_does_not_show_other_users_entries(self):
        """List view only shows current user's entries."""
        other_user = self._create_user(
            email='other@example.com',
            password='testpass123'
        )
        CaptureEntry.objects.create(
            user=other_user,
            title='Other User Recording',
            status=CaptureEntry.STATUS_READY,
        )
        response = self.client.get(reverse('capture:list'))
        self.assertNotContains(response, 'Other User Recording')

    def test_list_view_orders_by_created_at_desc(self):
        """List view orders entries by most recent first."""
        entry1 = CaptureEntry.objects.create(
            user=self.user,
            title='First Recording',
            status=CaptureEntry.STATUS_READY,
        )
        entry2 = CaptureEntry.objects.create(
            user=self.user,
            title='Second Recording',
            status=CaptureEntry.STATUS_READY,
        )
        response = self.client.get(reverse('capture:list'))
        entries = list(response.context['entries'])
        self.assertEqual(entries[0].id, entry2.id)
        self.assertEqual(entries[1].id, entry1.id)

    def test_list_view_context_has_counts(self):
        """List view context includes total and ready counts."""
        CaptureEntry.objects.create(
            user=self.user,
            title='Ready Entry',
            status=CaptureEntry.STATUS_READY,
        )
        CaptureEntry.objects.create(
            user=self.user,
            title='Processing Entry',
            status=CaptureEntry.STATUS_TRANSCRIBING,
        )
        response = self.client.get(reverse('capture:list'))
        self.assertEqual(response.context['total_count'], 2)
        self.assertEqual(response.context['ready_count'], 1)

    def test_list_view_shows_status(self):
        """List view displays entry status correctly."""
        CaptureEntry.objects.create(
            user=self.user,
            title='Ready Entry',
            status=CaptureEntry.STATUS_READY,
        )
        response = self.client.get(reverse('capture:list'))
        self.assertContains(response, 'Ready')

    def test_list_view_shows_failed_status(self):
        """List view displays failed status."""
        CaptureEntry.objects.create(
            user=self.user,
            title='Failed Entry',
            status=CaptureEntry.STATUS_FAILED,
        )
        response = self.client.get(reverse('capture:list'))
        self.assertContains(response, 'Failed')

    def test_list_view_shows_untitled_for_no_title(self):
        """List view shows 'Untitled Recording' when no title."""
        CaptureEntry.objects.create(
            user=self.user,
            title='',
            status=CaptureEntry.STATUS_READY,
        )
        response = self.client.get(reverse('capture:list'))
        self.assertContains(response, 'Untitled Recording')

    def test_list_view_shows_category(self):
        """List view displays entry category."""
        CaptureEntry.objects.create(
            user=self.user,
            title='Faith Entry',
            category=CaptureEntry.CATEGORY_FAITH,
            subcategory=CaptureEntry.SUBCATEGORY_SERMON,
            status=CaptureEntry.STATUS_READY,
        )
        response = self.client.get(reverse('capture:list'))
        self.assertContains(response, 'Faith')
        self.assertContains(response, 'Sermon')


class CaptureRecordViewTests(TestCase):
    """Tests for CaptureRecordView."""

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

    def test_record_view_requires_login(self):
        """Record view requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('capture:record'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_record_view_loads(self):
        """Record view loads for authenticated user."""
        response = self.client.get(reverse('capture:record'))
        self.assertEqual(response.status_code, 200)

    def test_record_view_uses_correct_template(self):
        """Record view uses the correct template."""
        response = self.client.get(reverse('capture:record'))
        self.assertTemplateUsed(response, 'capture/capture_record.html')

    def test_record_view_contains_recording_interface(self):
        """Record view contains the recording interface elements."""
        response = self.client.get(reverse('capture:record'))
        self.assertContains(response, 'recording-interface')
        self.assertContains(response, 'start-recording')
        self.assertContains(response, 'stop-recording')

    def test_record_view_contains_browser_support_check(self):
        """Record view contains browser support check elements."""
        response = self.client.get(reverse('capture:record'))
        self.assertContains(response, 'unsupported-browser')
        self.assertContains(response, 'MediaRecorder')

    def test_record_view_contains_permission_handling(self):
        """Record view contains permission handling elements."""
        response = self.client.get(reverse('capture:record'))
        self.assertContains(response, 'permission-denied')
        self.assertContains(response, 'Microphone Access Denied')

    def test_record_view_contains_preview_controls(self):
        """Record view contains preview controls."""
        response = self.client.get(reverse('capture:record'))
        self.assertContains(response, 'audio-preview')
        self.assertContains(response, 'discard-recording')
        self.assertContains(response, 'submit-recording')

    def test_record_view_has_max_duration_info(self):
        """Record view displays maximum duration information."""
        response = self.client.get(reverse('capture:record'))
        self.assertContains(response, '60 minutes')


class CaptureUploadViewTests(TestCase):
    """Tests for CaptureUploadView."""

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

    def test_upload_view_requires_login(self):
        """Upload view requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('capture:upload'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_upload_view_loads(self):
        """Upload view loads for authenticated user."""
        response = self.client.get(reverse('capture:upload'))
        self.assertEqual(response.status_code, 200)

    def test_upload_view_uses_correct_template(self):
        """Upload view uses the correct template."""
        response = self.client.get(reverse('capture:upload'))
        self.assertTemplateUsed(response, 'capture/capture_upload.html')

    def test_upload_view_contains_drop_zone(self):
        """Upload view contains drop zone elements."""
        response = self.client.get(reverse('capture:upload'))
        self.assertContains(response, 'drop-zone')
        self.assertContains(response, 'Drop your audio file here')

    def test_upload_view_contains_file_input(self):
        """Upload view contains file input with correct accept attribute."""
        response = self.client.get(reverse('capture:upload'))
        self.assertContains(response, 'file-input')
        self.assertContains(response, '.mp3')
        self.assertContains(response, '.m4a')
        self.assertContains(response, '.wav')
        self.assertContains(response, '.webm')

    def test_upload_view_shows_accepted_formats(self):
        """Upload view displays accepted formats info."""
        response = self.client.get(reverse('capture:upload'))
        self.assertContains(response, 'MP3')
        self.assertContains(response, 'M4A')
        self.assertContains(response, 'WAV')
        self.assertContains(response, 'WebM')

    def test_upload_view_shows_max_size(self):
        """Upload view displays maximum file size."""
        response = self.client.get(reverse('capture:upload'))
        self.assertContains(response, '60MB')

    def test_upload_view_contains_progress_indicator(self):
        """Upload view contains upload progress indicator."""
        response = self.client.get(reverse('capture:upload'))
        self.assertContains(response, 'upload-progress')
        self.assertContains(response, 'progress-bar')

    def test_upload_post_requires_file(self):
        """Upload POST without file returns error."""
        response = self.client.post(reverse('capture:upload'))
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_upload_rejects_invalid_file_type(self):
        """Upload rejects non-audio file types."""
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile

        fake_file = SimpleUploadedFile(
            'test.txt',
            b'not an audio file',
            content_type='text/plain'
        )
        response = self.client.post(
            reverse('capture:upload'),
            {'file': fake_file}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid file type', response.json().get('error', ''))

    def test_upload_rejects_oversized_file(self):
        """Upload rejects files over 60MB."""
        from unittest.mock import patch, MagicMock
        from django.core.files.uploadedfile import SimpleUploadedFile

        fake_file = SimpleUploadedFile(
            'test.mp3',
            b'fake audio content',
            content_type='audio/mpeg'
        )

        # Patch the validation method to simulate a large file
        from apps.capture.views import CaptureUploadView
        original_validate = CaptureUploadView._validate_file

        def mock_validate(self, file):
            # Override size check to simulate large file
            if file.name == 'test.mp3':
                return False, 'File too large. Maximum size is 60MB.'
            return original_validate(self, file)

        with patch.object(CaptureUploadView, '_validate_file', mock_validate):
            response = self.client.post(
                reverse('capture:upload'),
                {'file': fake_file}
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn('too large', response.json().get('error', ''))

    def test_upload_accepts_valid_mp3(self):
        """Upload accepts valid MP3 file."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        fake_file = SimpleUploadedFile(
            'test.mp3',
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
        self.assertIn('entry_id', data)

    def test_upload_accepts_valid_m4a(self):
        """Upload accepts valid M4A file."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        fake_file = SimpleUploadedFile(
            'test.m4a',
            b'fake audio content',
            content_type='audio/mp4'
        )
        response = self.client.post(
            reverse('capture:upload'),
            {'file': fake_file}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))

    def test_upload_accepts_valid_wav(self):
        """Upload accepts valid WAV file."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        fake_file = SimpleUploadedFile(
            'test.wav',
            b'fake audio content',
            content_type='audio/wav'
        )
        response = self.client.post(
            reverse('capture:upload'),
            {'file': fake_file}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))

    def test_upload_accepts_valid_webm(self):
        """Upload accepts valid WebM file."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        fake_file = SimpleUploadedFile(
            'test.webm',
            b'fake audio content',
            content_type='audio/webm'
        )
        response = self.client.post(
            reverse('capture:upload'),
            {'file': fake_file}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))

    def test_upload_creates_capture_entry(self):
        """Upload creates CaptureEntry for valid file."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        initial_count = CaptureEntry.objects.filter(user=self.user).count()

        fake_file = SimpleUploadedFile(
            'my_recording.mp3',
            b'fake audio content',
            content_type='audio/mpeg'
        )
        response = self.client.post(
            reverse('capture:upload'),
            {'file': fake_file}
        )
        self.assertEqual(response.status_code, 200)

        new_count = CaptureEntry.objects.filter(user=self.user).count()
        self.assertEqual(new_count, initial_count + 1)

        # Check entry title is from filename (without extension)
        entry = CaptureEntry.objects.filter(user=self.user).first()
        self.assertEqual(entry.title, 'my_recording')

    def test_chunked_upload_init(self):
        """Chunked upload initialization works."""
        import json

        response = self.client.post(
            reverse('capture:upload'),
            data=json.dumps({
                'action': 'init_chunked',
                'filename': 'test.mp3',
                'filesize': 10 * 1024 * 1024,  # 10MB
                'total_chunks': 2
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertIn('session_id', data)

    def test_chunked_upload_init_rejects_invalid_extension(self):
        """Chunked upload init rejects invalid file extension."""
        import json

        response = self.client.post(
            reverse('capture:upload'),
            data=json.dumps({
                'action': 'init_chunked',
                'filename': 'test.exe',
                'filesize': 10 * 1024 * 1024,
                'total_chunks': 2
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid file type', response.json().get('error', ''))

    def test_chunked_upload_init_rejects_oversized(self):
        """Chunked upload init rejects files over 60MB."""
        import json

        response = self.client.post(
            reverse('capture:upload'),
            data=json.dumps({
                'action': 'init_chunked',
                'filename': 'test.mp3',
                'filesize': 70 * 1024 * 1024,  # 70MB
                'total_chunks': 14
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('too large', response.json().get('error', ''))


class CaptureNavigationTests(TestCase):
    """Tests for Capture navigation presence in nav and dashboard."""

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

    def test_capture_in_navigation_when_enabled(self):
        """Capture link appears in navigation when capture is enabled."""
        self.user.preferences.capture_enabled = True
        self.user.preferences.save()

        response = self.client.get(reverse('dashboard:home'))
        self.assertContains(response, 'Capture')
        self.assertContains(response, reverse('capture:list'))

    def test_capture_not_in_navigation_when_disabled(self):
        """Capture link not in navigation when capture is disabled."""
        self.user.preferences.capture_enabled = False
        self.user.preferences.save()

        response = self.client.get(reverse('dashboard:home'))
        self.assertNotContains(response, reverse('capture:list'))

    def test_capture_quick_action_when_enabled(self):
        """Record Audio quick action appears on dashboard when capture is enabled."""
        self.user.preferences.capture_enabled = True
        self.user.preferences.save()

        response = self.client.get(reverse('dashboard:home'))
        self.assertContains(response, 'Record Audio')
        self.assertContains(response, reverse('capture:record'))

    def test_capture_quick_action_not_when_disabled(self):
        """Record Audio quick action not shown when capture is disabled."""
        self.user.preferences.capture_enabled = False
        self.user.preferences.save()

        response = self.client.get(reverse('dashboard:home'))
        self.assertNotContains(response, reverse('capture:record'))

    def test_capture_module_card_when_enabled(self):
        """Capture module card appears on dashboard when capture is enabled."""
        self.user.preferences.capture_enabled = True
        self.user.preferences.save()

        response = self.client.get(reverse('dashboard:home'))
        # Check for the module card with recording count
        self.assertContains(response, '0 recordings')


class CaptureSubmitViewTests(TestCase):
    """Tests for CaptureSubmitView (S3 presigned URL generation)."""

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

    def test_submit_requires_login(self):
        """Submit view requires authentication."""
        self.client.logout()
        response = self.client.post(
            reverse('capture:submit'),
            data='{"action": "get_upload_url"}',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_submit_requires_json(self):
        """Submit view requires JSON content type."""
        response = self.client.post(
            reverse('capture:submit'),
            data='not json',
            content_type='text/plain'
        )
        self.assertEqual(response.status_code, 400)

    def test_submit_requires_valid_action(self):
        """Submit view requires a valid action."""
        import json
        response = self.client.post(
            reverse('capture:submit'),
            data=json.dumps({'action': 'invalid'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid action', response.json().get('error', ''))

    def test_get_upload_url_invalid_content_type(self):
        """get_upload_url rejects invalid content types."""
        import json
        response = self.client.post(
            reverse('capture:submit'),
            data=json.dumps({
                'action': 'get_upload_url',
                'content_type': 'text/plain'
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid content type', response.json().get('error', ''))

    def test_get_upload_url_mock_mode(self):
        """get_upload_url returns mock response when S3 not configured."""
        import json
        response = self.client.post(
            reverse('capture:submit'),
            data=json.dumps({
                'action': 'get_upload_url',
                'content_type': 'audio/webm',
                'filename': 'test_recording.webm',
                'title': 'Test Recording',
                'duration_seconds': 120
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertIn('entry_id', data)
        # In mock mode, upload_url is None
        self.assertTrue(data.get('mock_mode') or data.get('upload_url'))

    def test_get_upload_url_creates_entry(self):
        """get_upload_url creates a CaptureEntry."""
        import json
        initial_count = CaptureEntry.objects.filter(user=self.user).count()

        response = self.client.post(
            reverse('capture:submit'),
            data=json.dumps({
                'action': 'get_upload_url',
                'content_type': 'audio/webm',
                'title': 'My Recording'
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        new_count = CaptureEntry.objects.filter(user=self.user).count()
        self.assertEqual(new_count, initial_count + 1)

        entry = CaptureEntry.objects.filter(user=self.user).first()
        self.assertEqual(entry.title, 'My Recording')

    def test_confirm_upload_requires_entry_id(self):
        """confirm_upload requires entry_id."""
        import json
        response = self.client.post(
            reverse('capture:submit'),
            data=json.dumps({'action': 'confirm_upload'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Missing entry_id', response.json().get('error', ''))

    def test_confirm_upload_validates_entry_exists(self):
        """confirm_upload returns 404 for non-existent entry."""
        import json
        import uuid
        response = self.client.post(
            reverse('capture:submit'),
            data=json.dumps({
                'action': 'confirm_upload',
                'entry_id': str(uuid.uuid4())
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

    def test_confirm_upload_validates_ownership(self):
        """confirm_upload only allows user to confirm their own entries."""
        import json
        # Create entry for another user
        other_user = self._create_user(email='other@example.com')
        entry = CaptureEntry.objects.create(
            user=other_user,
            title='Other User Entry',
            status=CaptureEntry.STATUS_UPLOADING
        )

        response = self.client.post(
            reverse('capture:submit'),
            data=json.dumps({
                'action': 'confirm_upload',
                'entry_id': str(entry.id)
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

    def test_confirm_upload_validates_status(self):
        """confirm_upload only works on entries with uploading status."""
        import json
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Already Ready Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:submit'),
            data=json.dumps({
                'action': 'confirm_upload',
                'entry_id': str(entry.id)
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('not in uploading status', response.json().get('error', ''))

    def test_confirm_upload_success(self):
        """confirm_upload updates status to transcribing."""
        import json
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Uploading Entry',
            status=CaptureEntry.STATUS_UPLOADING
        )

        response = self.client.post(
            reverse('capture:submit'),
            data=json.dumps({
                'action': 'confirm_upload',
                'entry_id': str(entry.id)
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('status'), CaptureEntry.STATUS_TRANSCRIBING)

        # Verify entry status updated
        entry.refresh_from_db()
        self.assertEqual(entry.status, CaptureEntry.STATUS_TRANSCRIBING)


class CaptureStatusViewTests(TestCase):
    """Tests for CaptureStatusView (status polling)."""

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

    def test_status_requires_login(self):
        """Status view requires authentication."""
        import uuid
        self.client.logout()
        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': uuid.uuid4()})
        )
        self.assertEqual(response.status_code, 302)

    def test_status_returns_404_for_nonexistent_entry(self):
        """Status view returns 404 for non-existent entry."""
        import uuid
        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': uuid.uuid4()})
        )
        self.assertEqual(response.status_code, 404)

    def test_status_returns_404_for_other_users_entry(self):
        """Status view returns 404 for another user's entry."""
        other_user = self._create_user(email='other@example.com')
        entry = CaptureEntry.objects.create(
            user=other_user,
            title='Other User Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': entry.id})
        )
        self.assertEqual(response.status_code, 404)

    def test_status_returns_entry_status(self):
        """Status view returns current entry status."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='My Entry',
            status=CaptureEntry.STATUS_TRANSCRIBING
        )

        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': entry.id})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), CaptureEntry.STATUS_TRANSCRIBING)
        self.assertEqual(data.get('title'), 'My Entry')

    def test_status_includes_error_for_failed_entries(self):
        """Status view includes error message for failed entries."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Failed Entry',
            status=CaptureEntry.STATUS_FAILED,
            error_message='Transcription failed due to audio quality'
        )

        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': entry.id})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), CaptureEntry.STATUS_FAILED)
        self.assertIn('audio quality', data.get('error_message', ''))

    def test_status_includes_summary_for_ready_entries(self):
        """Status view includes summary for ready entries."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Ready Entry',
            status=CaptureEntry.STATUS_READY,
            summary='This is the summary',
            transcript='This is the full transcript',
            category='faith',
            subcategory='sermon'
        )

        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': entry.id})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), CaptureEntry.STATUS_READY)
        self.assertEqual(data.get('summary'), 'This is the summary')
        self.assertEqual(data.get('category'), 'faith')
        self.assertEqual(data.get('subcategory'), 'sermon')

    def test_status_includes_user_friendly_message_uploading(self):
        """Status view includes user-friendly message for uploading status."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Uploading Entry',
            status=CaptureEntry.STATUS_UPLOADING
        )

        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': entry.id})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status_message'), 'Uploading')
        self.assertEqual(data.get('status_description'), 'Uploading your recording...')
        self.assertEqual(data.get('progress'), 25)

    def test_status_includes_user_friendly_message_transcribing(self):
        """Status view includes user-friendly message for transcribing status."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Transcribing Entry',
            status=CaptureEntry.STATUS_TRANSCRIBING
        )

        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': entry.id})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status_message'), 'Transcribing')
        self.assertEqual(data.get('status_description'), 'Converting speech to text...')
        self.assertEqual(data.get('progress'), 50)

    def test_status_includes_user_friendly_message_summarizing(self):
        """Status view includes user-friendly message for summarizing status."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Summarizing Entry',
            status=CaptureEntry.STATUS_SUMMARIZING
        )

        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': entry.id})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status_message'), 'Summarizing')
        self.assertEqual(data.get('status_description'), 'Generating AI summary...')
        self.assertEqual(data.get('progress'), 75)

    def test_status_includes_user_friendly_message_ready(self):
        """Status view includes user-friendly message for ready status."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Ready Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': entry.id})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status_message'), 'Ready')
        self.assertEqual(data.get('status_description'), 'Your recording is ready!')
        self.assertEqual(data.get('progress'), 100)

    def test_status_includes_user_friendly_message_failed(self):
        """Status view includes user-friendly message for failed status."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Failed Entry',
            status=CaptureEntry.STATUS_FAILED,
            error_message='Something went wrong'
        )

        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': entry.id})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status_message'), 'Failed')
        self.assertEqual(data.get('status_description'), 'Processing failed')
        self.assertEqual(data.get('progress'), 0)
        self.assertEqual(data.get('error_message'), 'Something went wrong')

    def test_status_includes_redirect_url_for_ready_entries(self):
        """Status view includes redirect URL for ready entries."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Ready Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': entry.id})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('redirect_url'), reverse('capture:detail', kwargs={'pk': entry.id}))

    def test_status_no_redirect_url_for_non_ready_entries(self):
        """Status view does not include redirect URL for non-ready entries."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Processing Entry',
            status=CaptureEntry.STATUS_TRANSCRIBING
        )

        response = self.client.get(
            reverse('capture:status', kwargs={'entry_id': entry.id})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn('redirect_url', data)


class CaptureDetailViewTests(TestCase):
    """Tests for CaptureDetailView."""

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

    def test_detail_view_requires_login(self):
        """Detail view requires authentication."""
        import uuid
        self.client.logout()
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )
        response = self.client.get(
            reverse('capture:detail', kwargs={'pk': entry.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_detail_view_returns_404_for_nonexistent_entry(self):
        """Detail view returns 404 for non-existent entry."""
        import uuid
        response = self.client.get(
            reverse('capture:detail', kwargs={'pk': uuid.uuid4()})
        )
        self.assertEqual(response.status_code, 404)

    def test_detail_view_returns_404_for_other_users_entry(self):
        """Detail view returns 404 for another user's entry."""
        other_user = self._create_user(email='other@example.com')
        entry = CaptureEntry.objects.create(
            user=other_user,
            title='Other User Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.get(
            reverse('capture:detail', kwargs={'pk': entry.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_detail_view_displays_entry(self):
        """Detail view displays entry for authenticated owner."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='My Test Entry',
            status=CaptureEntry.STATUS_READY,
            summary='This is the test summary.',
            category='faith',
            subcategory='sermon'
        )

        response = self.client.get(
            reverse('capture:detail', kwargs={'pk': entry.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Test Entry')
        self.assertContains(response, 'This is the test summary.')
        self.assertContains(response, 'Faith')
        self.assertContains(response, 'Sermon')

    def test_detail_view_uses_correct_template(self):
        """Detail view uses the correct template."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Template Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.get(
            reverse('capture:detail', kwargs={'pk': entry.pk})
        )
        self.assertTemplateUsed(response, 'capture/capture_detail.html')

    def test_detail_view_shows_formatted_duration(self):
        """Detail view shows formatted duration."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Duration Test',
            status=CaptureEntry.STATUS_READY,
            duration_seconds=125  # 2 minutes 5 seconds
        )

        response = self.client.get(
            reverse('capture:detail', kwargs={'pk': entry.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['formatted_duration'], '2:05')

    def test_detail_view_shows_transcript_section(self):
        """Detail view shows transcript section when transcript exists."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Transcript Test',
            status=CaptureEntry.STATUS_READY,
            transcript='This is the full transcript of the recording.'
        )

        response = self.client.get(
            reverse('capture:detail', kwargs={'pk': entry.pk})
        )
        self.assertContains(response, 'Full Transcript')
        self.assertContains(response, 'This is the full transcript')

    def test_detail_view_shows_processing_status_for_non_ready(self):
        """Detail view shows processing status for entries not yet ready."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Processing Entry',
            status=CaptureEntry.STATUS_TRANSCRIBING
        )

        response = self.client.get(
            reverse('capture:detail', kwargs={'pk': entry.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Transcribing')

    def test_detail_view_shows_error_for_failed_entry(self):
        """Detail view shows error message for failed entries."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Failed Entry',
            status=CaptureEntry.STATUS_FAILED,
            error_message='Transcription failed due to audio quality'
        )

        response = self.client.get(
            reverse('capture:detail', kwargs={'pk': entry.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Processing Failed')
        self.assertContains(response, 'audio quality')

    def test_detail_view_shows_audio_player_when_url_exists(self):
        """Detail view shows audio player when audio URL exists."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Audio Test',
            status=CaptureEntry.STATUS_READY,
            audio_file_url='https://example.com/audio.mp3'
        )

        response = self.client.get(
            reverse('capture:detail', kwargs={'pk': entry.pk})
        )
        self.assertContains(response, 'Audio Recording')
        self.assertContains(response, 'https://example.com/audio.mp3')
        self.assertContains(response, 'Download Audio')


class CaptureUpdateTitleViewTests(TestCase):
    """Tests for CaptureUpdateTitleView."""

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

    def test_update_title_requires_login(self):
        """Update title endpoint requires authentication."""
        self.client.logout()
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )
        response = self.client.post(
            reverse('capture:update_title', kwargs={'pk': entry.pk}),
            data=json.dumps({'title': 'New Title'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_update_title_returns_404_for_nonexistent_entry(self):
        """Update title returns 404 for non-existent entry."""
        import uuid
        response = self.client.post(
            reverse('capture:update_title', kwargs={'pk': uuid.uuid4()}),
            data=json.dumps({'title': 'New Title'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

    def test_update_title_returns_404_for_other_users_entry(self):
        """Update title returns 404 for another user's entry."""
        other_user = self._create_user(email='other@example.com')
        entry = CaptureEntry.objects.create(
            user=other_user,
            title='Other User Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:update_title', kwargs={'pk': entry.pk}),
            data=json.dumps({'title': 'Hacked Title'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

        # Verify title wasn't changed
        entry.refresh_from_db()
        self.assertEqual(entry.title, 'Other User Entry')

    def test_update_title_success(self):
        """Update title successfully updates entry title."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Original Title',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:update_title', kwargs={'pk': entry.pk}),
            data=json.dumps({'title': 'New Title'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('title'), 'New Title')
        self.assertEqual(data.get('message'), 'Title updated successfully')

        # Verify database was updated
        entry.refresh_from_db()
        self.assertEqual(entry.title, 'New Title')

    def test_update_title_strips_whitespace(self):
        """Update title strips leading/trailing whitespace."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Original Title',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:update_title', kwargs={'pk': entry.pk}),
            data=json.dumps({'title': '  New Title  '}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('title'), 'New Title')

        entry.refresh_from_db()
        self.assertEqual(entry.title, 'New Title')

    def test_update_title_allows_empty_title(self):
        """Update title allows empty/blank title."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Original Title',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:update_title', kwargs={'pk': entry.pk}),
            data=json.dumps({'title': ''}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('title'), '')

        entry.refresh_from_db()
        self.assertEqual(entry.title, '')

    def test_update_title_rejects_too_long(self):
        """Update title rejects titles over 200 characters."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Original Title',
            status=CaptureEntry.STATUS_READY
        )

        long_title = 'A' * 201  # 201 characters

        response = self.client.post(
            reverse('capture:update_title', kwargs={'pk': entry.pk}),
            data=json.dumps({'title': long_title}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('200', data['error'])

        # Verify title wasn't changed
        entry.refresh_from_db()
        self.assertEqual(entry.title, 'Original Title')

    def test_update_title_accepts_max_length(self):
        """Update title accepts titles exactly 200 characters."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Original Title',
            status=CaptureEntry.STATUS_READY
        )

        exact_title = 'A' * 200  # Exactly 200 characters

        response = self.client.post(
            reverse('capture:update_title', kwargs={'pk': entry.pk}),
            data=json.dumps({'title': exact_title}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(len(data.get('title')), 200)

        entry.refresh_from_db()
        self.assertEqual(entry.title, exact_title)

    def test_update_title_rejects_invalid_json(self):
        """Update title rejects invalid JSON body."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Original Title',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:update_title', kwargs={'pk': entry.pk}),
            data='not valid json',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('JSON', data['error'])


class CaptureUpdateCategoryViewTests(TestCase):
    """Tests for CaptureUpdateCategoryView."""

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

    def test_update_category_requires_login(self):
        """Update category endpoint requires authentication."""
        self.client.logout()
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )
        response = self.client.post(
            reverse('capture:update_category', kwargs={'pk': entry.pk}),
            data=json.dumps({'category': 'faith'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_update_category_returns_404_for_nonexistent_entry(self):
        """Update category returns 404 for non-existent entry."""
        import uuid
        response = self.client.post(
            reverse('capture:update_category', kwargs={'pk': uuid.uuid4()}),
            data=json.dumps({'category': 'faith'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

    def test_update_category_returns_404_for_other_users_entry(self):
        """Update category returns 404 for another user's entry."""
        other_user = self._create_user(email='other@example.com')
        entry = CaptureEntry.objects.create(
            user=other_user,
            title='Other User Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:update_category', kwargs={'pk': entry.pk}),
            data=json.dumps({'category': 'faith'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

        # Verify category wasn't changed
        entry.refresh_from_db()
        self.assertEqual(entry.category, '')

    def test_update_category_success_faith(self):
        """Update category successfully sets faith category."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:update_category', kwargs={'pk': entry.pk}),
            data=json.dumps({'category': 'faith'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('category'), 'faith')
        self.assertEqual(data.get('category_display'), 'Faith')
        self.assertEqual(data.get('message'), 'Category updated successfully')

        # Verify database was updated
        entry.refresh_from_db()
        self.assertEqual(entry.category, 'faith')

    def test_update_category_success_organize(self):
        """Update category successfully sets organize category."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:update_category', kwargs={'pk': entry.pk}),
            data=json.dumps({'category': 'organize'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('category'), 'organize')
        self.assertEqual(data.get('category_display'), 'Organize')

        entry.refresh_from_db()
        self.assertEqual(entry.category, 'organize')

    def test_update_category_with_subcategory_faith_sermon(self):
        """Update category with faith/sermon subcategory."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:update_category', kwargs={'pk': entry.pk}),
            data=json.dumps({'category': 'faith', 'subcategory': 'sermon'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('category'), 'faith')
        self.assertEqual(data.get('subcategory'), 'sermon')
        self.assertEqual(data.get('subcategory_display'), 'Sermon')

        entry.refresh_from_db()
        self.assertEqual(entry.category, 'faith')
        self.assertEqual(entry.subcategory, 'sermon')

    def test_update_category_with_subcategory_faith_bible_study(self):
        """Update category with faith/bible_study subcategory."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:update_category', kwargs={'pk': entry.pk}),
            data=json.dumps({'category': 'faith', 'subcategory': 'bible_study'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('subcategory'), 'bible_study')
        self.assertEqual(data.get('subcategory_display'), 'Bible Study')

    def test_update_category_with_subcategory_organize_meeting(self):
        """Update category with organize/meeting subcategory."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:update_category', kwargs={'pk': entry.pk}),
            data=json.dumps({'category': 'organize', 'subcategory': 'meeting'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('category'), 'organize')
        self.assertEqual(data.get('subcategory'), 'meeting')
        self.assertEqual(data.get('subcategory_display'), 'Meeting')

        entry.refresh_from_db()
        self.assertEqual(entry.category, 'organize')
        self.assertEqual(entry.subcategory, 'meeting')

    def test_update_category_rejects_invalid_category(self):
        """Update category rejects invalid category value."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:update_category', kwargs={'pk': entry.pk}),
            data=json.dumps({'category': 'invalid_category'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('Invalid category', data['error'])

        # Verify category wasn't changed
        entry.refresh_from_db()
        self.assertEqual(entry.category, '')

    def test_update_category_rejects_subcategory_without_category(self):
        """Update category rejects subcategory without a category."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:update_category', kwargs={'pk': entry.pk}),
            data=json.dumps({'subcategory': 'sermon'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('Cannot set subcategory without a category', data['error'])

    def test_update_category_rejects_mismatched_subcategory(self):
        """Update category rejects subcategory that doesn't match category."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        # Try to set faith category with organize subcategory
        response = self.client.post(
            reverse('capture:update_category', kwargs={'pk': entry.pk}),
            data=json.dumps({'category': 'faith', 'subcategory': 'meeting'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('Invalid subcategory', data['error'])

    def test_update_category_clears_category(self):
        """Update category clears category when empty string."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY,
            category='faith',
            subcategory='sermon'
        )

        response = self.client.post(
            reverse('capture:update_category', kwargs={'pk': entry.pk}),
            data=json.dumps({'category': ''}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('category'), '')
        self.assertEqual(data.get('subcategory'), '')

        entry.refresh_from_db()
        self.assertEqual(entry.category, '')
        self.assertEqual(entry.subcategory, '')

    def test_update_category_clears_subcategory_when_category_changes(self):
        """Update category clears subcategory when category changes without new subcategory."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY,
            category='faith',
            subcategory='sermon'
        )

        response = self.client.post(
            reverse('capture:update_category', kwargs={'pk': entry.pk}),
            data=json.dumps({'category': 'organize'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('category'), 'organize')
        self.assertEqual(data.get('subcategory'), '')

        entry.refresh_from_db()
        self.assertEqual(entry.category, 'organize')
        self.assertEqual(entry.subcategory, '')

    def test_update_category_rejects_invalid_json(self):
        """Update category rejects invalid JSON body."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:update_category', kwargs={'pk': entry.pk}),
            data='not valid json',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('JSON', data['error'])

    def test_update_category_strips_whitespace(self):
        """Update category strips leading/trailing whitespace."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:update_category', kwargs={'pk': entry.pk}),
            data=json.dumps({'category': '  faith  ', 'subcategory': '  sermon  '}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('category'), 'faith')
        self.assertEqual(data.get('subcategory'), 'sermon')

        entry.refresh_from_db()
        self.assertEqual(entry.category, 'faith')
        self.assertEqual(entry.subcategory, 'sermon')
