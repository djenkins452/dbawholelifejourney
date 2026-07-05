"""
Tests for journal signal extraction dispatch (request-path safe).

Covers:
  - _dispatch_signal_extraction: fire-and-forget via safe_enqueue, NO sync fallback
  - Broker-outage safety: no synchronous extraction on the save path
  - Idempotency: duplicate protection for the worker path
  - AI gate: extraction skipped when AI is disabled
  - Production logging: enqueue-failure warnings visible, not debug-only

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

    @patch("apps.core.celery_utils.safe_enqueue")
    def test_async_dispatch_uses_safe_enqueue(self, mock_enqueue):
        """Dispatch hands the task to the non-blocking safe_enqueue primitive.

        Request-path safety: extraction (which can call OpenAI) is enqueued
        fire-and-forget via safe_enqueue — never `.delay()` directly, never
        synchronously on the save path.
        """
        from apps.journal.signals import _dispatch_signal_extraction
        from apps.journal.tasks import extract_journal_signals

        entry = self._create_entry()
        mock_enqueue.reset_mock()

        _dispatch_signal_extraction(entry)
        mock_enqueue.assert_called_once_with(extract_journal_signals, entry.pk)

    @patch("apps.journal.services.signal_extractor.JournalSignalExtractor.extract_signals")
    @patch(
        "apps.journal.tasks.extract_journal_signals.apply_async",
        side_effect=ConnectionError("Redis unavailable"),
    )
    def test_no_sync_fallback_on_broker_failure(self, mock_async, mock_extract):
        """A broker outage must NOT trigger synchronous extraction.

        This is the core request-path guarantee: when async infrastructure is
        unavailable, safe_enqueue swallows the error and returns immediately.
        Eventual consistency is the worker's job (idempotency gate prevents
        duplicates), never a synchronous rebuild on the request thread.
        """
        from apps.journal.signals import _dispatch_signal_extraction

        entry = self._create_entry()
        mock_async.reset_mock()
        mock_extract.reset_mock()

        _dispatch_signal_extraction(entry)

        # Enqueue was attempted (and failed) — but NO synchronous extraction ran.
        self.assertTrue(mock_async.called)
        mock_extract.assert_not_called()

    @patch(
        "apps.journal.tasks.extract_journal_signals.apply_async",
        side_effect=ConnectionError("Redis unavailable"),
    )
    def test_enqueue_failure_logs_warning_and_never_raises(self, mock_async):
        """A failed enqueue logs a visible warning (from safe_enqueue) and
        never raises into the save path."""
        from apps.journal.signals import _dispatch_signal_extraction

        entry = self._create_entry()

        with self.assertLogs("apps.core.celery_utils", level="WARNING") as cm:
            _dispatch_signal_extraction(entry)  # must not raise

        self.assertTrue(
            any("async dispatch failed" in msg for msg in cm.output),
            f"Expected safe_enqueue warning in logs, got: {cm.output}",
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
