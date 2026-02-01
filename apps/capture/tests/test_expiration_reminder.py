"""Tests for capture audio expiration reminder functionality."""

from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.capture.models import CaptureEntry
from apps.capture.jobs import send_expiration_reminders
from apps.capture.services.expiration_reminder import send_expiration_reminder_email
from apps.users.models import User


class ExpirationReminderEmailTests(TestCase):
    """Tests for the expiration reminder email service."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
        )
        self.entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Recording',
            status=CaptureEntry.STATUS_READY,
            duration_seconds=300,  # 5 minutes
            audio_expires_at=timezone.now() + timedelta(days=2),
        )

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_expiration_reminder_email_success(self):
        """Test successfully sending an expiration reminder email."""
        result = send_expiration_reminder_email(self.entry)

        self.assertTrue(result['success'])
        self.assertEqual(len(mail.outbox), 1)

        email = mail.outbox[0]
        self.assertIn('Audio Expiring Soon', email.subject)
        self.assertIn('Test Recording', email.subject)
        self.assertEqual(email.to, ['test@example.com'])
        self.assertIn('Test Recording', email.body)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_expiration_reminder_email_untitled(self):
        """Test sending reminder for untitled recording."""
        self.entry.title = ''
        self.entry.save()

        result = send_expiration_reminder_email(self.entry)

        self.assertTrue(result['success'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Untitled Recording', mail.outbox[0].subject)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_expiration_reminder_email_no_duration(self):
        """Test sending reminder for entry without duration."""
        self.entry.duration_seconds = None
        self.entry.save()

        result = send_expiration_reminder_email(self.entry)

        self.assertTrue(result['success'])
        self.assertEqual(len(mail.outbox), 1)

    def test_send_expiration_reminder_email_failure(self):
        """Test handling email send failure."""
        with patch('apps.capture.services.expiration_reminder.EmailMessage') as mock_email:
            mock_instance = MagicMock()
            mock_instance.send.side_effect = Exception('SMTP error')
            mock_email.return_value = mock_instance

            result = send_expiration_reminder_email(self.entry)

            self.assertFalse(result['success'])
            self.assertIn('error', result)


class SendExpirationRemindersJobTests(TestCase):
    """Tests for the send_expiration_reminders job function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
        )
        self.user2 = User.objects.create_user(
            email='test2@example.com',
            password='testpass123',
        )

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_sends_reminders_for_entries_expiring_in_2_days(self):
        """Test that reminders are sent for entries expiring in 2 days."""
        # Create entry expiring in ~1.5 days (within the 1-2 day window)
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Expiring Soon',
            status=CaptureEntry.STATUS_READY,
            audio_expires_at=timezone.now() + timedelta(days=1, hours=12),
        )

        result = send_expiration_reminders()

        self.assertEqual(result['sent'], 1)
        self.assertEqual(result['failed'], 0)
        self.assertEqual(len(mail.outbox), 1)

        # Verify reminder_sent_at was set
        entry.refresh_from_db()
        self.assertIsNotNone(entry.reminder_sent_at)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_does_not_send_reminders_for_entries_expiring_beyond_2_days(self):
        """Test that reminders are not sent for entries expiring in more than 2 days."""
        CaptureEntry.objects.create(
            user=self.user,
            title='Not Expiring Soon',
            status=CaptureEntry.STATUS_READY,
            audio_expires_at=timezone.now() + timedelta(days=5),
        )

        result = send_expiration_reminders()

        self.assertEqual(result['sent'], 0)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_does_not_send_reminders_for_entries_expiring_within_1_day(self):
        """Test that reminders are not sent for entries expiring in less than 1 day."""
        CaptureEntry.objects.create(
            user=self.user,
            title='Expiring Very Soon',
            status=CaptureEntry.STATUS_READY,
            audio_expires_at=timezone.now() + timedelta(hours=12),
        )

        result = send_expiration_reminders()

        self.assertEqual(result['sent'], 0)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_does_not_send_reminder_twice(self):
        """Test that reminders are not sent if already sent."""
        CaptureEntry.objects.create(
            user=self.user,
            title='Already Reminded',
            status=CaptureEntry.STATUS_READY,
            audio_expires_at=timezone.now() + timedelta(days=1, hours=12),
            reminder_sent_at=timezone.now() - timedelta(hours=1),  # Already sent
        )

        result = send_expiration_reminders()

        self.assertEqual(result['sent'], 0)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_does_not_send_reminder_for_non_ready_entries(self):
        """Test that reminders are only sent for ready entries."""
        # Processing entry
        CaptureEntry.objects.create(
            user=self.user,
            title='Still Processing',
            status=CaptureEntry.STATUS_TRANSCRIBING,
            audio_expires_at=timezone.now() + timedelta(days=1, hours=12),
        )
        # Failed entry
        CaptureEntry.objects.create(
            user=self.user,
            title='Failed',
            status=CaptureEntry.STATUS_FAILED,
            audio_expires_at=timezone.now() + timedelta(days=1, hours=12),
        )

        result = send_expiration_reminders()

        self.assertEqual(result['sent'], 0)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_sends_reminders_to_multiple_users(self):
        """Test that reminders are sent to multiple users with expiring entries."""
        CaptureEntry.objects.create(
            user=self.user,
            title='User 1 Entry',
            status=CaptureEntry.STATUS_READY,
            audio_expires_at=timezone.now() + timedelta(days=1, hours=12),
        )
        CaptureEntry.objects.create(
            user=self.user2,
            title='User 2 Entry',
            status=CaptureEntry.STATUS_READY,
            audio_expires_at=timezone.now() + timedelta(days=1, hours=6),
        )

        result = send_expiration_reminders()

        self.assertEqual(result['sent'], 2)
        self.assertEqual(len(mail.outbox), 2)

        # Verify different recipients
        recipients = {mail.outbox[0].to[0], mail.outbox[1].to[0]}
        self.assertEqual(recipients, {'test@example.com', 'test2@example.com'})

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_does_not_send_reminder_for_entries_without_expiration(self):
        """Test that entries without audio_expires_at are skipped."""
        CaptureEntry.objects.create(
            user=self.user,
            title='No Expiration',
            status=CaptureEntry.STATUS_READY,
            audio_expires_at=None,
        )

        result = send_expiration_reminders()

        self.assertEqual(result['sent'], 0)
        self.assertEqual(len(mail.outbox), 0)


class CaptureEntryReminderFieldTests(TestCase):
    """Tests for the reminder_sent_at field on CaptureEntry."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
        )

    def test_reminder_sent_at_field_exists(self):
        """Test that reminder_sent_at field exists and is nullable."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test',
            status=CaptureEntry.STATUS_READY,
        )

        self.assertIsNone(entry.reminder_sent_at)

    def test_reminder_sent_at_can_be_set(self):
        """Test that reminder_sent_at can be set to a datetime."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test',
            status=CaptureEntry.STATUS_READY,
        )

        now = timezone.now()
        entry.reminder_sent_at = now
        entry.save()

        entry.refresh_from_db()
        self.assertIsNotNone(entry.reminder_sent_at)
        # Allow for small time differences
        self.assertAlmostEqual(
            entry.reminder_sent_at.timestamp(),
            now.timestamp(),
            delta=1
        )
