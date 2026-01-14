"""Tests for capture email sharing functionality."""

import json
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.capture.models import CaptureEntry

User = get_user_model()


class CaptureEmailServiceTests(TestCase):
    """Tests for the email service."""

    def setUp(self):
        """Set up test user and entries."""
        self.user = self._create_user()

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

    @patch('apps.capture.services.email.generate_pdf')
    @patch('apps.capture.services.email.get_pdf_filename')
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_capture_email_success(self, mock_filename, mock_pdf):
        """send_capture_email successfully sends email with PDF attachment."""
        from apps.capture.services.email import send_capture_email

        mock_pdf.return_value = b'%PDF-1.4 mock pdf content'
        mock_filename.return_value = 'Test Entry - WLJ Capture - 2026-01-14.pdf'

        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY,
            summary='Test summary'
        )

        result = send_capture_email(
            capture_entry=entry,
            recipient_email='recipient@example.com',
            sender_user=self.user,
            message='Check this out!'
        )

        self.assertTrue(result['success'])
        self.assertEqual(len(mail.outbox), 1)

        sent_email = mail.outbox[0]
        self.assertIn('Test Entry', sent_email.subject)
        self.assertEqual(sent_email.to, ['recipient@example.com'])
        self.assertEqual(len(sent_email.attachments), 1)
        self.assertEqual(sent_email.attachments[0][0], 'Test Entry - WLJ Capture - 2026-01-14.pdf')

    def test_send_capture_email_invalid_email(self):
        """send_capture_email rejects invalid email addresses."""
        from apps.capture.services.email import send_capture_email

        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        result = send_capture_email(
            capture_entry=entry,
            recipient_email='not-an-email',
            sender_user=self.user
        )

        self.assertFalse(result['success'])
        self.assertIn('Invalid email', result['error'])

    @patch('apps.capture.services.email.generate_pdf')
    def test_send_capture_email_pdf_generation_fails(self, mock_pdf):
        """send_capture_email handles PDF generation failure."""
        from apps.capture.services.email import send_capture_email

        mock_pdf.side_effect = ImportError('WeasyPrint not installed')

        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        result = send_capture_email(
            capture_entry=entry,
            recipient_email='recipient@example.com',
            sender_user=self.user
        )

        self.assertFalse(result['success'])
        self.assertIn('not available', result['error'])

    @patch('apps.capture.services.email.generate_pdf')
    @patch('apps.capture.services.email.get_pdf_filename')
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_capture_email_without_message(self, mock_filename, mock_pdf):
        """send_capture_email works without optional message."""
        from apps.capture.services.email import send_capture_email

        mock_pdf.return_value = b'mock pdf'
        mock_filename.return_value = 'test.pdf'

        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        result = send_capture_email(
            capture_entry=entry,
            recipient_email='recipient@example.com',
            sender_user=self.user,
            message=None
        )

        self.assertTrue(result['success'])
        self.assertEqual(len(mail.outbox), 1)

    @patch('apps.capture.services.email.generate_pdf')
    @patch('apps.capture.services.email.get_pdf_filename')
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_capture_email_subject_format(self, mock_filename, mock_pdf):
        """send_capture_email uses correct subject format."""
        from apps.capture.services.email import send_capture_email

        mock_pdf.return_value = b'mock pdf'
        mock_filename.return_value = 'test.pdf'

        # Set user name for testing
        self.user.first_name = 'John'
        self.user.last_name = 'Doe'
        self.user.save()

        entry = CaptureEntry.objects.create(
            user=self.user,
            title='My Recording',
            status=CaptureEntry.STATUS_READY
        )

        result = send_capture_email(
            capture_entry=entry,
            recipient_email='recipient@example.com',
            sender_user=self.user
        )

        self.assertTrue(result['success'])
        sent_email = mail.outbox[0]
        self.assertIn('John Doe', sent_email.subject)
        self.assertIn('My Recording', sent_email.subject)
        self.assertIn('WLJ Capture', sent_email.subject)


class CaptureEmailViewTests(TestCase):
    """Tests for CaptureEmailView."""

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

    def test_email_requires_login(self):
        """Email endpoint requires authentication."""
        self.client.logout()
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )
        response = self.client.post(
            reverse('capture:send_email', kwargs={'pk': entry.pk}),
            data=json.dumps({'recipient_email': 'test@example.com'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_email_returns_404_for_nonexistent_entry(self):
        """Email returns 404 for non-existent entry."""
        import uuid
        response = self.client.post(
            reverse('capture:send_email', kwargs={'pk': uuid.uuid4()}),
            data=json.dumps({'recipient_email': 'test@example.com'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

    def test_email_returns_404_for_other_users_entry(self):
        """Email returns 404 for another user's entry."""
        other_user = self._create_user(email='other@example.com')
        entry = CaptureEntry.objects.create(
            user=other_user,
            title='Other User Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:send_email', kwargs={'pk': entry.pk}),
            data=json.dumps({'recipient_email': 'test@example.com'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

    def test_email_rejects_non_ready_entries(self):
        """Email rejects entries that are not ready."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Processing Entry',
            status=CaptureEntry.STATUS_TRANSCRIBING
        )

        response = self.client.post(
            reverse('capture:send_email', kwargs={'pk': entry.pk}),
            data=json.dumps({'recipient_email': 'test@example.com'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('not ready', data.get('error', ''))

    def test_email_requires_recipient_email(self):
        """Email requires recipient_email in request body."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:send_email', kwargs={'pk': entry.pk}),
            data=json.dumps({}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('required', data.get('error', ''))

    def test_email_rejects_empty_recipient_email(self):
        """Email rejects empty recipient email."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:send_email', kwargs={'pk': entry.pk}),
            data=json.dumps({'recipient_email': '   '}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    @patch('apps.capture.services.email.send_capture_email')
    def test_email_success(self, mock_send):
        """Email returns success for valid request."""
        mock_send.return_value = {'success': True}

        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:send_email', kwargs={'pk': entry.pk}),
            data=json.dumps({
                'recipient_email': 'recipient@example.com',
                'message': 'Check this out!'
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('recipient@example.com', data['message'])

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs['recipient_email'], 'recipient@example.com')
        self.assertEqual(call_kwargs['message'], 'Check this out!')

    @patch('apps.capture.services.email.send_capture_email')
    def test_email_handles_service_error(self, mock_send):
        """Email returns error when service fails."""
        mock_send.return_value = {
            'success': False,
            'error': 'Failed to send email'
        }

        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:send_email', kwargs={'pk': entry.pk}),
            data=json.dumps({'recipient_email': 'recipient@example.com'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Failed to send', data['error'])

    def test_email_rejects_invalid_json(self):
        """Email returns error for invalid JSON."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:send_email', kwargs={'pk': entry.pk}),
            data='not json',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('Invalid JSON', data.get('error', ''))

    @patch('apps.capture.services.email.send_capture_email')
    def test_email_without_message(self, mock_send):
        """Email works without optional message."""
        mock_send.return_value = {'success': True}

        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Entry',
            status=CaptureEntry.STATUS_READY
        )

        response = self.client.post(
            reverse('capture:send_email', kwargs={'pk': entry.pk}),
            data=json.dumps({'recipient_email': 'recipient@example.com'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertIsNone(call_kwargs['message'])
