"""Tests for capture models."""

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from apps.capture.models import CaptureEntry

User = get_user_model()


class CaptureEntryModelTests(TestCase):
    """Tests for the CaptureEntry model."""

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='testpass123'
        )

    def test_create_minimal_entry(self):
        """Test creating entry with minimal required fields."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Recording'
        )
        self.assertIsNotNone(entry.id)
        self.assertIsInstance(entry.id, uuid.UUID)
        self.assertEqual(entry.title, 'Test Recording')
        self.assertEqual(entry.status, CaptureEntry.STATUS_UPLOADING)
        self.assertIsNotNone(entry.created_at)
        self.assertIsNotNone(entry.updated_at)

    def test_entry_uuid_is_unique(self):
        """Test that each entry gets a unique UUID."""
        entry1 = CaptureEntry.objects.create(user=self.user, title='Entry 1')
        entry2 = CaptureEntry.objects.create(user=self.user, title='Entry 2')
        self.assertNotEqual(entry1.id, entry2.id)

    def test_entry_with_all_fields(self):
        """Test creating entry with all fields populated."""
        expires_at = timezone.now() + timedelta(days=7)
        reminder_at = timezone.now() - timedelta(hours=1)

        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Complete Recording',
            duration_seconds=3600,
            audio_file_url='https://s3.example.com/audio.mp3',
            audio_expires_at=expires_at,
            transcript='This is the full transcript.',
            summary='This is the summary.',
            category=CaptureEntry.CATEGORY_FAITH,
            subcategory=CaptureEntry.SUBCATEGORY_SERMON,
            status=CaptureEntry.STATUS_READY,
            error_message='',
            reminder_sent_at=reminder_at,
        )

        self.assertEqual(entry.duration_seconds, 3600)
        self.assertEqual(entry.audio_file_url, 'https://s3.example.com/audio.mp3')
        self.assertEqual(entry.transcript, 'This is the full transcript.')
        self.assertEqual(entry.summary, 'This is the summary.')
        self.assertEqual(entry.category, CaptureEntry.CATEGORY_FAITH)
        self.assertEqual(entry.subcategory, CaptureEntry.SUBCATEGORY_SERMON)
        self.assertEqual(entry.status, CaptureEntry.STATUS_READY)
        self.assertIsNotNone(entry.audio_expires_at)
        self.assertIsNotNone(entry.reminder_sent_at)


class CaptureEntryStatusTests(TestCase):
    """Tests for CaptureEntry status handling."""

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='testpass123'
        )

    def test_default_status_is_uploading(self):
        """Test that default status is 'uploading'."""
        entry = CaptureEntry.objects.create(user=self.user, title='Test')
        self.assertEqual(entry.status, CaptureEntry.STATUS_UPLOADING)

    def test_all_status_choices_are_valid(self):
        """Test that all status choices can be set."""
        for status, display in CaptureEntry.STATUS_CHOICES:
            entry = CaptureEntry.objects.create(
                user=self.user,
                title=f'Status {status}',
                status=status
            )
            self.assertEqual(entry.status, status)
            self.assertEqual(entry.get_status_display(), display)

    def test_status_transition_uploading_to_transcribing(self):
        """Test transitioning from uploading to transcribing."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test',
            status=CaptureEntry.STATUS_UPLOADING
        )
        entry.status = CaptureEntry.STATUS_TRANSCRIBING
        entry.save()

        entry.refresh_from_db()
        self.assertEqual(entry.status, CaptureEntry.STATUS_TRANSCRIBING)

    def test_status_transition_transcribing_to_summarizing(self):
        """Test transitioning from transcribing to summarizing."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test',
            status=CaptureEntry.STATUS_TRANSCRIBING
        )
        entry.status = CaptureEntry.STATUS_SUMMARIZING
        entry.save()

        entry.refresh_from_db()
        self.assertEqual(entry.status, CaptureEntry.STATUS_SUMMARIZING)

    def test_status_transition_summarizing_to_ready(self):
        """Test transitioning from summarizing to ready."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test',
            status=CaptureEntry.STATUS_SUMMARIZING
        )
        entry.status = CaptureEntry.STATUS_READY
        entry.save()

        entry.refresh_from_db()
        self.assertEqual(entry.status, CaptureEntry.STATUS_READY)

    def test_status_transition_to_failed(self):
        """Test transitioning to failed from any status."""
        for status, _ in CaptureEntry.STATUS_CHOICES:
            if status == CaptureEntry.STATUS_FAILED:
                continue
            entry = CaptureEntry.objects.create(
                user=self.user,
                title=f'Entry {status}',
                status=status
            )
            entry.status = CaptureEntry.STATUS_FAILED
            entry.error_message = 'Something went wrong'
            entry.save()

            entry.refresh_from_db()
            self.assertEqual(entry.status, CaptureEntry.STATUS_FAILED)
            self.assertEqual(entry.error_message, 'Something went wrong')


class CaptureEntryCategoryTests(TestCase):
    """Tests for CaptureEntry category and subcategory handling."""

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='testpass123'
        )

    def test_all_category_choices_are_valid(self):
        """Test that all category choices can be set."""
        for category, display in CaptureEntry.CATEGORY_CHOICES:
            entry = CaptureEntry.objects.create(
                user=self.user,
                title=f'Category {category}',
                category=category
            )
            self.assertEqual(entry.category, category)
            self.assertEqual(entry.get_category_display(), display)

    def test_all_subcategory_choices_are_valid(self):
        """Test that all subcategory choices can be set."""
        for subcategory, display in CaptureEntry.SUBCATEGORY_CHOICES:
            entry = CaptureEntry.objects.create(
                user=self.user,
                title=f'Subcategory {subcategory}',
                subcategory=subcategory
            )
            self.assertEqual(entry.subcategory, subcategory)
            self.assertEqual(entry.get_subcategory_display(), display)

    def test_faith_category_with_sermon_subcategory(self):
        """Test faith category with sermon subcategory."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Sunday Sermon',
            category=CaptureEntry.CATEGORY_FAITH,
            subcategory=CaptureEntry.SUBCATEGORY_SERMON
        )
        self.assertEqual(entry.get_category_display(), 'Faith')
        self.assertEqual(entry.get_subcategory_display(), 'Sermon')

    def test_faith_category_with_bible_study_subcategory(self):
        """Test faith category with bible study subcategory."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Bible Study',
            category=CaptureEntry.CATEGORY_FAITH,
            subcategory=CaptureEntry.SUBCATEGORY_BIBLE_STUDY
        )
        self.assertEqual(entry.get_category_display(), 'Faith')
        self.assertEqual(entry.get_subcategory_display(), 'Bible Study')

    def test_organize_category_with_meeting_subcategory(self):
        """Test organize category with meeting subcategory."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Team Meeting',
            category=CaptureEntry.CATEGORY_ORGANIZE,
            subcategory=CaptureEntry.SUBCATEGORY_MEETING
        )
        self.assertEqual(entry.get_category_display(), 'Organize')
        self.assertEqual(entry.get_subcategory_display(), 'Meeting')

    def test_category_and_subcategory_can_be_blank(self):
        """Test that category and subcategory can be left blank."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Uncategorized',
            category='',
            subcategory=''
        )
        self.assertEqual(entry.category, '')
        self.assertEqual(entry.subcategory, '')


class CaptureEntryStrTests(TestCase):
    """Tests for CaptureEntry __str__ method."""

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='testpass123'
        )

    def test_str_with_title(self):
        """Test __str__ with title returns title and status."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='My Recording',
            status=CaptureEntry.STATUS_READY
        )
        self.assertEqual(str(entry), 'My Recording (Ready)')

    def test_str_without_title(self):
        """Test __str__ without title returns id and status."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='',
            status=CaptureEntry.STATUS_TRANSCRIBING
        )
        expected = f'Capture {entry.id} (Transcribing)'
        self.assertEqual(str(entry), expected)

    def test_str_with_different_statuses(self):
        """Test __str__ with different status values."""
        status_tests = [
            (CaptureEntry.STATUS_UPLOADING, 'Uploading'),
            (CaptureEntry.STATUS_TRANSCRIBING, 'Transcribing'),
            (CaptureEntry.STATUS_SUMMARIZING, 'Summarizing'),
            (CaptureEntry.STATUS_READY, 'Ready'),
            (CaptureEntry.STATUS_FAILED, 'Failed'),
        ]
        for status, display in status_tests:
            entry = CaptureEntry.objects.create(
                user=self.user,
                title='Test',
                status=status
            )
            self.assertIn(display, str(entry))


class CaptureEntryOrderingTests(TestCase):
    """Tests for CaptureEntry ordering."""

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='testpass123'
        )

    def test_default_ordering_is_created_at_desc(self):
        """Test that entries are ordered by created_at descending."""
        entry1 = CaptureEntry.objects.create(user=self.user, title='First')
        entry2 = CaptureEntry.objects.create(user=self.user, title='Second')
        entry3 = CaptureEntry.objects.create(user=self.user, title='Third')

        entries = list(CaptureEntry.objects.all())
        # Most recent first
        self.assertEqual(entries[0].id, entry3.id)
        self.assertEqual(entries[1].id, entry2.id)
        self.assertEqual(entries[2].id, entry1.id)


class CaptureEntryUserRelationshipTests(TestCase):
    """Tests for CaptureEntry user relationship."""

    def setUp(self):
        """Set up test users."""
        self.user1 = User.objects.create_user(
            email='user1@example.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            email='user2@example.com',
            password='testpass123'
        )

    def test_entry_belongs_to_user(self):
        """Test that entry is associated with correct user."""
        entry = CaptureEntry.objects.create(
            user=self.user1,
            title='User 1 Entry'
        )
        self.assertEqual(entry.user, self.user1)
        self.assertEqual(entry.user.email, 'user1@example.com')

    def test_user_can_have_multiple_entries(self):
        """Test that a user can have multiple entries."""
        entry1 = CaptureEntry.objects.create(user=self.user1, title='Entry 1')
        entry2 = CaptureEntry.objects.create(user=self.user1, title='Entry 2')
        entry3 = CaptureEntry.objects.create(user=self.user1, title='Entry 3')

        user_entries = CaptureEntry.objects.filter(user=self.user1)
        self.assertEqual(user_entries.count(), 3)

    def test_capture_entries_related_name(self):
        """Test accessing entries via user.capture_entries."""
        CaptureEntry.objects.create(user=self.user1, title='Entry 1')
        CaptureEntry.objects.create(user=self.user1, title='Entry 2')

        entries = self.user1.capture_entries.all()
        self.assertEqual(entries.count(), 2)

    def test_entries_isolated_between_users(self):
        """Test that entries are isolated between users."""
        CaptureEntry.objects.create(user=self.user1, title='User 1 Entry')
        CaptureEntry.objects.create(user=self.user2, title='User 2 Entry')

        user1_entries = CaptureEntry.objects.filter(user=self.user1)
        user2_entries = CaptureEntry.objects.filter(user=self.user2)

        self.assertEqual(user1_entries.count(), 1)
        self.assertEqual(user2_entries.count(), 1)
        self.assertEqual(user1_entries.first().title, 'User 1 Entry')
        self.assertEqual(user2_entries.first().title, 'User 2 Entry')

    def test_cascade_delete_on_user(self):
        """Test that entries are deleted when user is deleted."""
        CaptureEntry.objects.create(user=self.user1, title='Entry 1')
        CaptureEntry.objects.create(user=self.user1, title='Entry 2')

        self.assertEqual(CaptureEntry.objects.filter(user=self.user1).count(), 2)

        self.user1.delete()

        self.assertEqual(CaptureEntry.objects.filter(user=self.user1).count(), 0)


class CaptureEntryDurationTests(TestCase):
    """Tests for CaptureEntry duration_seconds field."""

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='testpass123'
        )

    def test_duration_can_be_null(self):
        """Test that duration_seconds can be null."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='No Duration',
            duration_seconds=None
        )
        self.assertIsNone(entry.duration_seconds)

    def test_duration_zero(self):
        """Test that duration can be zero."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Zero Duration',
            duration_seconds=0
        )
        self.assertEqual(entry.duration_seconds, 0)

    def test_duration_short_recording(self):
        """Test short recording duration (1 minute)."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Short Recording',
            duration_seconds=60
        )
        self.assertEqual(entry.duration_seconds, 60)

    def test_duration_max_recording(self):
        """Test maximum recording duration (60 minutes)."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Max Recording',
            duration_seconds=3600  # 60 minutes
        )
        self.assertEqual(entry.duration_seconds, 3600)

    def test_duration_large_value(self):
        """Test that large duration values are stored correctly."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Long Recording',
            duration_seconds=86400  # 24 hours
        )
        self.assertEqual(entry.duration_seconds, 86400)


class CaptureEntryAudioExpirationTests(TestCase):
    """Tests for CaptureEntry audio expiration handling."""

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='testpass123'
        )

    def test_audio_expires_at_can_be_null(self):
        """Test that audio_expires_at can be null."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='No Expiration',
            audio_expires_at=None
        )
        self.assertIsNone(entry.audio_expires_at)

    def test_audio_expires_at_can_be_set(self):
        """Test setting audio_expires_at."""
        expires_at = timezone.now() + timedelta(days=7)
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='With Expiration',
            audio_expires_at=expires_at
        )
        self.assertIsNotNone(entry.audio_expires_at)

    def test_audio_url_with_expiration(self):
        """Test audio_file_url and audio_expires_at together."""
        expires_at = timezone.now() + timedelta(days=7)
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Complete Audio',
            audio_file_url='https://s3.example.com/audio.mp3',
            audio_expires_at=expires_at
        )
        self.assertEqual(entry.audio_file_url, 'https://s3.example.com/audio.mp3')
        self.assertIsNotNone(entry.audio_expires_at)


class CaptureEntryReminderTests(TestCase):
    """Tests for CaptureEntry reminder_sent_at field."""

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='testpass123'
        )

    def test_reminder_sent_at_default_is_null(self):
        """Test that reminder_sent_at defaults to null."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test'
        )
        self.assertIsNone(entry.reminder_sent_at)

    def test_reminder_sent_at_can_be_set(self):
        """Test setting reminder_sent_at."""
        now = timezone.now()
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test',
            reminder_sent_at=now
        )
        entry.refresh_from_db()
        self.assertIsNotNone(entry.reminder_sent_at)

    def test_reminder_sent_at_can_be_updated(self):
        """Test updating reminder_sent_at."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test'
        )
        self.assertIsNone(entry.reminder_sent_at)

        now = timezone.now()
        entry.reminder_sent_at = now
        entry.save()

        entry.refresh_from_db()
        self.assertIsNotNone(entry.reminder_sent_at)


class CaptureEntryTranscriptSummaryTests(TestCase):
    """Tests for CaptureEntry transcript and summary fields."""

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='testpass123'
        )

    def test_transcript_can_be_empty(self):
        """Test that transcript can be empty."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='No Transcript',
            transcript=''
        )
        self.assertEqual(entry.transcript, '')

    def test_summary_can_be_empty(self):
        """Test that summary can be empty."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='No Summary',
            summary=''
        )
        self.assertEqual(entry.summary, '')

    def test_long_transcript(self):
        """Test storing a long transcript."""
        long_text = 'This is a very long transcript. ' * 1000
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Long Transcript',
            transcript=long_text
        )
        entry.refresh_from_db()
        self.assertEqual(entry.transcript, long_text)

    def test_long_summary(self):
        """Test storing a long summary."""
        long_text = 'This is a summary. ' * 500
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Long Summary',
            summary=long_text
        )
        entry.refresh_from_db()
        self.assertEqual(entry.summary, long_text)

    def test_transcript_with_special_characters(self):
        """Test transcript with special characters."""
        transcript = "It's a test with \"quotes\" and <tags> & symbols!"
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Special Characters',
            transcript=transcript
        )
        entry.refresh_from_db()
        self.assertEqual(entry.transcript, transcript)

    def test_transcript_with_unicode(self):
        """Test transcript with unicode characters."""
        transcript = "Hello! \u00e9\u00e8\u00ea \u4e2d\u6587 \U0001F600"
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Unicode Transcript',
            transcript=transcript
        )
        entry.refresh_from_db()
        self.assertEqual(entry.transcript, transcript)


class CaptureEntryErrorMessageTests(TestCase):
    """Tests for CaptureEntry error_message field."""

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='testpass123'
        )

    def test_error_message_default_is_empty(self):
        """Test that error_message defaults to empty."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test'
        )
        self.assertEqual(entry.error_message, '')

    def test_error_message_can_be_set(self):
        """Test setting error_message."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Failed Entry',
            status=CaptureEntry.STATUS_FAILED,
            error_message='Transcription service unavailable'
        )
        self.assertEqual(entry.error_message, 'Transcription service unavailable')

    def test_long_error_message(self):
        """Test storing a long error message."""
        long_error = 'Error: ' + 'x' * 1000
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Long Error',
            status=CaptureEntry.STATUS_FAILED,
            error_message=long_error
        )
        entry.refresh_from_db()
        self.assertEqual(entry.error_message, long_error)


class CaptureEntryTitleTests(TestCase):
    """Tests for CaptureEntry title field."""

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='testpass123'
        )

    def test_title_can_be_empty(self):
        """Test that title can be empty."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title=''
        )
        self.assertEqual(entry.title, '')

    def test_title_max_length(self):
        """Test title at max length (255 chars)."""
        long_title = 'A' * 255
        entry = CaptureEntry.objects.create(
            user=self.user,
            title=long_title
        )
        self.assertEqual(len(entry.title), 255)

    def test_title_with_special_characters(self):
        """Test title with special characters."""
        special_title = "Test: Recording - \"Special\" <Edition>"
        entry = CaptureEntry.objects.create(
            user=self.user,
            title=special_title
        )
        self.assertEqual(entry.title, special_title)

    def test_title_with_unicode(self):
        """Test title with unicode characters."""
        unicode_title = "Sermon \u00e9\u00e8\u00ea \U0001F64F"
        entry = CaptureEntry.objects.create(
            user=self.user,
            title=unicode_title
        )
        entry.refresh_from_db()
        self.assertEqual(entry.title, unicode_title)


class CaptureEntryIndexTests(TestCase):
    """Tests for CaptureEntry database indexes."""

    def test_indexes_are_defined(self):
        """Test that expected indexes are defined."""
        meta = CaptureEntry._meta
        index_fields = [
            tuple(index.fields) for index in meta.indexes
        ]

        # Check expected indexes exist
        self.assertIn(('user', '-created_at'), index_fields)
        self.assertIn(('status', '-created_at'), index_fields)
        self.assertIn(('category', '-created_at'), index_fields)

    def test_status_field_has_db_index(self):
        """Test that status field has db_index=True."""
        status_field = CaptureEntry._meta.get_field('status')
        self.assertTrue(status_field.db_index)


class CaptureEntryMetaTests(TestCase):
    """Tests for CaptureEntry Meta options."""

    def test_verbose_name(self):
        """Test verbose_name is set correctly."""
        self.assertEqual(CaptureEntry._meta.verbose_name, 'Capture Entry')

    def test_verbose_name_plural(self):
        """Test verbose_name_plural is set correctly."""
        self.assertEqual(CaptureEntry._meta.verbose_name_plural, 'Capture Entries')

    def test_ordering(self):
        """Test default ordering is by -created_at."""
        self.assertEqual(CaptureEntry._meta.ordering, ['-created_at'])
