"""
Tests for journal signal extraction dispatch and sync fallback.

Covers:
  - _dispatch_signal_extraction: async primary, sync fallback
  - Idempotency: duplicate protection when both paths run
  - AI gate: extraction skipped when AI is disabled
  - Production logging: warnings visible, not debug-only

Project: Whole Life Journey
Path: apps/journal/tests/test_signal_extraction.py
"""

from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase

from apps.users.models import TermsAcceptance


class SignalExtractionDispatchTests(TestCase):
    """Test _dispatch_signal_extraction async/sync behavior."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user(
            email="journal-signal-test@example.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.ai_enabled = True
        self.user.preferences.personal_assistant_enabled = True
        self.user.preferences.save()

    def _create_entry(self, body="Test journal entry with enough words for extraction threshold."):
        from apps.journal.models import JournalEntry

        return JournalEntry.objects.create(
            user=self.user,
            title="Test Entry",
            body=body,
        )

    @patch("apps.journal.signals._dispatch_signal_extraction")
    def test_post_save_calls_dispatch(self, mock_dispatch):
        """Creating a journal entry should trigger signal dispatch."""
        entry = self._create_entry()
        mock_dispatch.assert_called_once_with(entry)

    @patch("apps.journal.signals._dispatch_signal_extraction")
    def test_post_save_skips_on_update(self, mock_dispatch):
        """Updating an existing entry should NOT trigger extraction."""
        entry = self._create_entry()
        mock_dispatch.reset_mock()

        entry.body = "Updated body text"
        entry.save()
        mock_dispatch.assert_not_called()

    @patch("apps.journal.signals._dispatch_signal_extraction")
    def test_post_save_skips_when_ai_disabled(self, mock_dispatch):
        """Should not dispatch when ai_enabled is False."""
        self.user.preferences.ai_enabled = False
        self.user.preferences.save()

        self._create_entry()
        mock_dispatch.assert_not_called()

    @patch("apps.journal.signals._dispatch_signal_extraction")
    def test_post_save_skips_when_assistant_disabled(self, mock_dispatch):
        """Should not dispatch when personal_assistant_enabled is False."""
        self.user.preferences.personal_assistant_enabled = False
        self.user.preferences.save()

        self._create_entry()
        mock_dispatch.assert_not_called()

    @patch("apps.journal.tasks.extract_journal_signals.delay")
    def test_async_dispatch_succeeds(self, mock_delay):
        """When Celery is available, async dispatch is used."""
        from apps.journal.signals import _dispatch_signal_extraction

        entry = self._create_entry()
        mock_delay.reset_mock()

        _dispatch_signal_extraction(entry)
        mock_delay.assert_called_once_with(entry.pk)

    @patch("apps.journal.services.signal_extractor.JournalSignalExtractor.extract_signals")
    @patch("apps.journal.tasks.extract_journal_signals.delay", side_effect=ConnectionError("Redis unavailable"))
    def test_sync_fallback_on_celery_failure(self, mock_delay, mock_extract):
        """When Celery dispatch fails, sync extraction should run."""
        from apps.journal.signals import _dispatch_signal_extraction

        # Create entry (triggers post_save which also hits the mock)
        entry = self._create_entry()
        mock_delay.reset_mock()
        mock_extract.reset_mock()
        mock_extract.return_value = []

        # Explicit call to test the function directly
        _dispatch_signal_extraction(entry)

        mock_delay.assert_called_once_with(entry.pk)
        mock_extract.assert_called_once_with(entry)

    @patch("apps.journal.services.signal_extractor.JournalSignalExtractor.extract_signals")
    @patch("apps.journal.tasks.extract_journal_signals.delay", side_effect=ConnectionError("Redis unavailable"))
    def test_sync_fallback_logs_warning(self, mock_delay, mock_extract):
        """Sync fallback should log at WARNING level (visible in production)."""
        from apps.journal.signals import _dispatch_signal_extraction

        entry = self._create_entry()
        mock_extract.return_value = []

        with self.assertLogs("apps.journal.signals", level="WARNING") as cm:
            _dispatch_signal_extraction(entry)

        self.assertTrue(
            any("falling back to synchronous" in msg for msg in cm.output),
            f"Expected fallback warning in logs, got: {cm.output}",
        )


class SignalExtractionIdempotencyTests(TestCase):
    """Test duplicate protection across async + sync paths."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user(
            email="journal-idempotency@example.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.ai_enabled = True
        self.user.preferences.personal_assistant_enabled = True
        self.user.preferences.save()

    def test_idempotency_gate_prevents_duplicates(self):
        """If signals already exist for an entry, extraction should skip."""
        from apps.journal.models import JournalEntry, JournalSignal
        from apps.journal.services.signal_extractor import JournalSignalExtractor

        entry = JournalEntry.objects.create(
            user=self.user,
            title="Test",
            body="Today I went for a long walk in the park and felt really good about my progress on the project. I am grateful for the sunshine and fresh air that helped clear my mind.",
        )

        # Simulate signals already created (e.g., by sync fallback)
        JournalSignal.objects.create(
            entry=entry,
            signal_type="mental_reflection",
            domain="mind",
            confidence=0.8,
            extracted_text="test signal",
        )

        # Extraction should return empty — idempotency gate blocks it
        with patch.object(JournalSignalExtractor, '_call_openai') as mock_openai:
            result = JournalSignalExtractor.extract_signals(entry)
            self.assertEqual(result, [])
            mock_openai.assert_not_called()

    def test_no_signals_allows_extraction(self):
        """Entry with no existing signals should proceed to extraction."""
        from apps.journal.models import JournalEntry
        from apps.journal.services.signal_extractor import JournalSignalExtractor

        entry = JournalEntry.objects.create(
            user=self.user,
            title="Test",
            body="Today I went for a long walk in the park and felt really good about my progress on the project. I am grateful for the sunshine and fresh air that helped clear my mind.",
        )

        # Mock OpenAI to return a valid signal
        mock_response = [
            {
                "signal_type": "mental_reflection",
                "domain": "mind",
                "confidence": 0.9,
                "extracted_text": "sufficiently long journal entry",
            }
        ]
        with patch.object(JournalSignalExtractor, '_call_openai', return_value=mock_response):
            result = JournalSignalExtractor.extract_signals(entry)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].signal_type, "mental_reflection")
            self.assertEqual(result[0].domain, "mind")
