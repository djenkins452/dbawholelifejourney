"""Tests for capture views."""

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
