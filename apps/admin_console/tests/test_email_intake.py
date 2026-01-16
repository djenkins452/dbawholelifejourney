# ==============================================================================
# File: apps/admin_console/tests/test_email_intake.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for email intake service
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-16
# ==============================================================================
"""
Tests for the email intake service.

Tests cover:
- Email parsing (MIME decoding, body extraction)
- Task creation from parsed emails
- Error handling
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
from apps.admin_console.services.email_intake import (
    EmailIntakeError,
    ParsedEmail,
    create_task_from_email,
    decode_mime_header,
    extract_email_body,
    get_email_settings,
    parse_email_message,
)


class DecodeHeaderTests(TestCase):
    """Tests for MIME header decoding."""

    def test_plain_text_header(self):
        """Plain text headers pass through unchanged."""
        result = decode_mime_header("Hello World")
        self.assertEqual(result, "Hello World")

    def test_empty_header(self):
        """Empty headers return empty string."""
        result = decode_mime_header("")
        self.assertEqual(result, "")

    def test_none_header(self):
        """None returns empty string."""
        result = decode_mime_header(None)
        self.assertEqual(result, "")

    def test_utf8_encoded_header(self):
        """UTF-8 MIME encoded headers are decoded."""
        # Example: =?UTF-8?Q?Test=20Subject?=
        encoded = "=?UTF-8?Q?Test=20Subject?="
        result = decode_mime_header(encoded)
        self.assertEqual(result, "Test Subject")

    def test_base64_encoded_header(self):
        """Base64 MIME encoded headers are decoded."""
        # Example: =?UTF-8?B?SGVsbG8gV29ybGQ=?= (Hello World in base64)
        encoded = "=?UTF-8?B?SGVsbG8gV29ybGQ=?="
        result = decode_mime_header(encoded)
        self.assertEqual(result, "Hello World")


class EmailSettingsTests(TestCase):
    """Tests for email settings retrieval."""

    @override_settings(
        EMAIL_INTAKE_HOST='imap.example.com',
        EMAIL_INTAKE_PORT=993,
        EMAIL_INTAKE_USER='test@example.com',
        EMAIL_INTAKE_PASSWORD='password123',
    )
    def test_get_settings_success(self):
        """Settings are retrieved correctly when all are present."""
        settings = get_email_settings()
        self.assertEqual(settings['host'], 'imap.example.com')
        self.assertEqual(settings['port'], 993)
        self.assertEqual(settings['user'], 'test@example.com')
        self.assertEqual(settings['password'], 'password123')

    @override_settings(
        EMAIL_INTAKE_HOST=None,
        EMAIL_INTAKE_USER='test@example.com',
        EMAIL_INTAKE_PASSWORD='password123',
    )
    def test_missing_host_raises_error(self):
        """Missing host raises EmailIntakeError."""
        with self.assertRaises(EmailIntakeError) as ctx:
            get_email_settings()
        self.assertIn('EMAIL_INTAKE_HOST', str(ctx.exception))

    @override_settings(
        EMAIL_INTAKE_HOST='imap.example.com',
        EMAIL_INTAKE_USER=None,
        EMAIL_INTAKE_PASSWORD='password123',
    )
    def test_missing_user_raises_error(self):
        """Missing user raises EmailIntakeError."""
        with self.assertRaises(EmailIntakeError) as ctx:
            get_email_settings()
        self.assertIn('EMAIL_INTAKE_USER', str(ctx.exception))


class ParseEmailTests(TestCase):
    """Tests for email message parsing."""

    def test_parse_simple_email(self):
        """Simple plain text email is parsed correctly."""
        raw_email = b"""From: John Doe <john@example.com>
To: admin@wholelifejourney.com
Subject: Test Email
Date: Thu, 16 Jan 2026 10:00:00 +0000
Message-ID: <123@example.com>
Content-Type: text/plain; charset="utf-8"

This is the email body.
"""
        parsed = parse_email_message("123", raw_email)

        self.assertEqual(parsed.uid, "123")
        self.assertEqual(parsed.subject, "Test Email")
        self.assertEqual(parsed.sender, "john@example.com")
        self.assertEqual(parsed.sender_name, "John Doe")
        self.assertEqual(parsed.message_id, "<123@example.com>")
        self.assertIn("This is the email body", parsed.body_text)

    def test_parse_multipart_email(self):
        """Multipart email extracts both text and HTML."""
        raw_email = b"""From: Jane Doe <jane@example.com>
To: admin@wholelifejourney.com
Subject: Multipart Test
Date: Thu, 16 Jan 2026 10:00:00 +0000
Message-ID: <456@example.com>
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="boundary123"

--boundary123
Content-Type: text/plain; charset="utf-8"

Plain text body.

--boundary123
Content-Type: text/html; charset="utf-8"

<html><body><p>HTML body.</p></body></html>

--boundary123--
"""
        parsed = parse_email_message("456", raw_email)

        self.assertEqual(parsed.subject, "Multipart Test")
        self.assertIn("Plain text body", parsed.body_text)
        self.assertIn("HTML body", parsed.body_html)


class CreateTaskFromEmailTests(TestCase):
    """Tests for creating AdminTask from parsed email."""

    def setUp(self):
        """Set up test data."""
        # Skip executable validation for test tasks
        AdminTask._skip_executable_validation = True

    def tearDown(self):
        """Reset test flags."""
        AdminTask._skip_executable_validation = False

    def test_creates_task_with_correct_fields(self):
        """Task is created with correct title, description, and metadata."""
        parsed = ParsedEmail(
            message_id="<test@example.com>",
            subject="Feature Request: Add dark mode",
            sender="user@example.com",
            sender_name="Test User",
            date=datetime(2026, 1, 16, 10, 0, 0, tzinfo=timezone.utc),
            body_text="Please add dark mode to the app. It would help reduce eye strain.",
            body_html="",
            uid="789",
        )

        task = create_task_from_email(parsed)

        self.assertIsNotNone(task.pk)
        self.assertIn("Feature Request", task.title)
        self.assertEqual(task.status, 'ready')
        self.assertEqual(task.created_by, 'claude')
        self.assertEqual(task.category, 'business')

        # Check description structure
        self.assertIn('objective', task.description)
        self.assertIn('inputs', task.description)
        self.assertIn('actions', task.description)
        self.assertIn('output', task.description)

        # Check inputs contain email metadata
        inputs_str = str(task.description['inputs'])
        self.assertIn('user@example.com', inputs_str)

    def test_creates_email_intake_project(self):
        """Creates Email Intake project if it doesn't exist."""
        parsed = ParsedEmail(
            message_id="<test@example.com>",
            subject="Test",
            sender="user@example.com",
            sender_name="User",
            date=None,
            body_text="Body",
            body_html="",
            uid="1",
        )

        create_task_from_email(parsed)

        # Project should be created
        project = AdminProject.objects.get(name='Email Intake')
        self.assertEqual(project.status, 'open')

    def test_creates_email_requests_phase(self):
        """Creates Email Requests phase if it doesn't exist."""
        parsed = ParsedEmail(
            message_id="<test@example.com>",
            subject="Test",
            sender="user@example.com",
            sender_name="User",
            date=None,
            body_text="Body",
            body_html="",
            uid="1",
        )

        create_task_from_email(parsed)

        # Phase should be created
        phase = AdminProjectPhase.objects.get(phase_number=999)
        self.assertEqual(phase.name, 'Email Requests')

    def test_truncates_long_subject(self):
        """Long email subjects are truncated in task title."""
        long_subject = "A" * 200  # 200 chars
        parsed = ParsedEmail(
            message_id="<test@example.com>",
            subject=long_subject,
            sender="user@example.com",
            sender_name="User",
            date=None,
            body_text="Body",
            body_html="",
            uid="1",
        )

        task = create_task_from_email(parsed)

        # Title should be truncated (Email: prefix + 150 chars max)
        self.assertLessEqual(len(task.title), 160)


class EmailIntakeIntegrationTests(TestCase):
    """Integration tests for full email intake flow."""

    def setUp(self):
        """Set up test data."""
        AdminTask._skip_executable_validation = True

    def tearDown(self):
        """Reset test flags."""
        AdminTask._skip_executable_validation = False

    @override_settings(
        EMAIL_INTAKE_HOST='mail.example.com',
        EMAIL_INTAKE_PORT=993,
        EMAIL_INTAKE_USER='admin@example.com',
        EMAIL_INTAKE_PASSWORD='password',
    )
    @patch('apps.admin_console.services.email_intake.connect_imap')
    @patch('apps.admin_console.services.email_intake.send_mail')
    def test_process_email_intake_dry_run(self, mock_send_mail, mock_connect):
        """Dry run processes emails without creating tasks."""
        from apps.admin_console.services.email_intake import process_email_intake

        # Mock IMAP connection
        mock_imap = MagicMock()
        mock_connect.return_value = mock_imap

        # Mock folder selection
        mock_imap.select.return_value = ('OK', [b'1'])

        # Mock search (no emails)
        mock_imap.uid.return_value = ('OK', [b''])

        results = process_email_intake(dry_run=True)

        self.assertEqual(results['processed'], 0)
        self.assertEqual(results['errors'], 0)
        mock_send_mail.assert_not_called()

    @override_settings(
        EMAIL_INTAKE_HOST='',
        EMAIL_INTAKE_USER='',
        EMAIL_INTAKE_PASSWORD='',
    )
    def test_process_email_intake_missing_settings(self):
        """Missing settings cause error."""
        from apps.admin_console.services.email_intake import process_email_intake

        results = process_email_intake()

        self.assertEqual(results['errors'], 1)
        self.assertIn('Missing required email settings', results['error_messages'][0])
