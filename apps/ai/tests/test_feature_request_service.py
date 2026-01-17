# ==============================================================================
# File: test_feature_request_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for the feature request detection service
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-10
# ==============================================================================
"""
Tests for Feature Request Detection Service

Tests pattern detection, rate limiting, and email notification functionality.
"""

from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.core import mail
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.ai.feature_request_service import (
    FeatureRequestService,
    FeatureRequestInfo,
    feature_request_service,
    COMPILED_PATTERNS,
)

User = get_user_model()


class FeatureRequestDetectionTests(TestCase):
    """Tests for detecting feature request patterns in messages."""

    def setUp(self):
        self.service = FeatureRequestService()

    def test_detect_i_wish_i_could(self):
        """Test detection of 'I wish I could' pattern."""
        message = "I wish I could track my sleep"
        is_request, pattern = self.service.detect_feature_request(message)
        self.assertTrue(is_request)
        self.assertIsNotNone(pattern)

    def test_detect_i_wish_the_app(self):
        """Test detection of 'I wish the app' pattern."""
        message = "I wish the app could send me reminders"
        is_request, pattern = self.service.detect_feature_request(message)
        self.assertTrue(is_request)

    def test_detect_i_want_to_be_able(self):
        """Test detection of 'I want to be able' pattern."""
        message = "I want to be able to export my data"
        is_request, pattern = self.service.detect_feature_request(message)
        self.assertTrue(is_request)

    def test_detect_i_want_the_ability(self):
        """Test detection of 'I want the ability' pattern."""
        message = "I want the ability to set custom goals"
        is_request, pattern = self.service.detect_feature_request(message)
        self.assertTrue(is_request)

    def test_detect_can_you_add(self):
        """Test detection of 'can you add' pattern."""
        message = "Can you add a dark mode feature?"
        is_request, pattern = self.service.detect_feature_request(message)
        self.assertTrue(is_request)

    def test_detect_could_you_create(self):
        """Test detection of 'could you create' pattern."""
        message = "Could you create a weekly summary report?"
        is_request, pattern = self.service.detect_feature_request(message)
        self.assertTrue(is_request)

    def test_detect_would_be_nice(self):
        """Test detection of 'it would be nice' pattern."""
        message = "It would be nice if I could see my progress over time"
        is_request, pattern = self.service.detect_feature_request(message)
        self.assertTrue(is_request)

    def test_detect_would_love_to(self):
        """Test detection of 'I would love to be able' pattern."""
        message = "I would love to be able to share my achievements"
        is_request, pattern = self.service.detect_feature_request(message)
        self.assertTrue(is_request)

    def test_detect_there_should_be(self):
        """Test detection of 'there should be' pattern."""
        message = "There should be a way to customize the dashboard"
        is_request, pattern = self.service.detect_feature_request(message)
        self.assertTrue(is_request)

    def test_detect_why_cant(self):
        """Test detection of 'why can't' pattern."""
        message = "Why can't I set multiple reminders?"
        is_request, pattern = self.service.detect_feature_request(message)
        self.assertTrue(is_request)

    def test_detect_feature_request_label(self):
        """Test detection of explicit feature request label."""
        message = "Feature request: add support for Apple Watch"
        is_request, pattern = self.service.detect_feature_request(message)
        self.assertTrue(is_request)

    def test_detect_please_add_feature(self):
        """Test detection of 'please add a feature' pattern."""
        message = "Please add a feature for meal planning"
        is_request, pattern = self.service.detect_feature_request(message)
        self.assertTrue(is_request)

    def test_no_detection_regular_message(self):
        """Test that regular messages don't trigger detection."""
        messages = [
            "How are you?",
            "What's my heart rate history?",
            "Tell me about fasting",
            "Should I take my medicine?",
            "My heart rate is 70",
            "I ate a banana",
            "Good morning",
        ]
        for message in messages:
            is_request, pattern = self.service.detect_feature_request(message)
            self.assertFalse(is_request, f"Should not detect: {message}")

    def test_no_detection_data_logging_want(self):
        """Test that 'I want to log' data messages don't trigger."""
        # These are data logging intents, not feature requests
        message = "I want to log my weight as 175"
        is_request, _ = self.service.detect_feature_request(message)
        # This should NOT match because it doesn't match our specific patterns
        # for feature requests (which look for "to be able", "the app", etc.)
        self.assertFalse(is_request)


class FeatureRequestRateLimitingTests(TestCase):
    """Tests for rate limiting feature request notifications."""

    def setUp(self):
        self.service = FeatureRequestService()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpassword123',
            first_name='Test',
            last_name='User'
        )
        # Use a simple dict to simulate cache since DummyCache doesn't persist
        self._cache_store = {}

    def tearDown(self):
        self._cache_store = {}

    @patch('apps.ai.feature_request_service.cache')
    def test_should_notify_first_request(self, mock_cache):
        """Test that first request should be notified."""
        mock_cache.get.return_value = None  # Not in cache
        message = "I wish I could track my sleep"
        self.assertTrue(self.service.should_notify(self.user, message))

    @patch('apps.ai.feature_request_service.cache')
    def test_should_not_notify_after_marking(self, mock_cache):
        """Test that repeated similar requests are rate limited."""
        message = "I wish I could track my sleep"

        # Simulate cache behavior
        cache_store = {}
        def get_side_effect(key, default=None):
            return cache_store.get(key, default)
        def set_side_effect(key, value, timeout=None):
            cache_store[key] = value

        mock_cache.get.side_effect = get_side_effect
        mock_cache.set.side_effect = set_side_effect

        # First time should allow
        self.assertTrue(self.service.should_notify(self.user, message))

        # Mark as notified
        self.service.mark_notified(self.user, message)

        # Second time should be rate limited
        self.assertFalse(self.service.should_notify(self.user, message))

    @patch('apps.ai.feature_request_service.cache')
    def test_different_messages_allowed(self, mock_cache):
        """Test that different messages are allowed through."""
        message1 = "I wish I could track my sleep"
        message2 = "I wish I could export my data to PDF"

        # Simulate cache behavior
        cache_store = {}
        def get_side_effect(key, default=None):
            return cache_store.get(key, default)
        def set_side_effect(key, value, timeout=None):
            cache_store[key] = value

        mock_cache.get.side_effect = get_side_effect
        mock_cache.set.side_effect = set_side_effect

        self.service.mark_notified(self.user, message1)

        # Different message should be allowed
        self.assertTrue(self.service.should_notify(self.user, message2))

    def test_key_word_extraction(self):
        """Test key word extraction for rate limiting."""
        message = "I wish I could track my sleep patterns"
        key_words = self.service._extract_key_words(message)

        # Should extract meaningful words, not stop words
        self.assertIn('track', key_words)
        self.assertIn('sleep', key_words)
        self.assertIn('patterns', key_words)
        self.assertNotIn('i', key_words)
        self.assertNotIn('could', key_words)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class FeatureRequestNotificationTests(TestCase):
    """Tests for email notification functionality."""

    def setUp(self):
        self.service = FeatureRequestService()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpassword123',
            first_name='Test',
            last_name='User'
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_send_notification_success(self):
        """Test that notification email is sent successfully."""
        request_info = FeatureRequestInfo(
            user_email='test@example.com',
            user_name='Test User',
            user_id=self.user.id,
            message='I wish I could track my sleep',
            detected_pattern='i wish i could',
            timestamp='2026-01-10 12:00:00 UTC',
        )

        result = self.service._send_notification(request_info)

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Feature Request', mail.outbox[0].subject)
        self.assertIn('Test User', mail.outbox[0].subject)

    def test_notification_contains_user_info(self):
        """Test that notification contains all required user information."""
        request_info = FeatureRequestInfo(
            user_email='test@example.com',
            user_name='Test User',
            user_id=self.user.id,
            message='I wish I could track my sleep patterns',
            detected_pattern='i wish i could',
            timestamp='2026-01-10 12:00:00 UTC',
        )

        self.service._send_notification(request_info)

        sent_email = mail.outbox[0]

        # Check plain text content
        self.assertIn('test@example.com', sent_email.body)
        self.assertIn('Test User', sent_email.body)
        self.assertIn('track my sleep', sent_email.body)
        self.assertIn('i wish i could', sent_email.body)

    def test_notification_with_conversation_context(self):
        """Test that conversation context is included when provided."""
        request_info = FeatureRequestInfo(
            user_email='test@example.com',
            user_name='Test User',
            user_id=self.user.id,
            message='I wish I could track my sleep',
            detected_pattern='i wish i could',
            timestamp='2026-01-10 12:00:00 UTC',
            conversation_context='User: Hello\nAssistant: Hi! How can I help?',
        )

        self.service._send_notification(request_info)

        sent_email = mail.outbox[0]
        self.assertIn('Hello', sent_email.body)
        self.assertIn('How can I help?', sent_email.body)

    def test_check_and_notify_full_flow(self):
        """Test the complete check and notify flow."""
        message = "I wish the app could remind me to take breaks"

        result = self.service.check_and_notify(
            user=self.user,
            message=message,
            intent_type='no_action',
        )

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)

    def test_check_and_notify_skips_actionable_intent(self):
        """Test that actionable intents don't trigger notification."""
        message = "I wish the app could remind me"

        result = self.service.check_and_notify(
            user=self.user,
            message=message,
            intent_type='log_heart_rate',  # Not 'no_action'
        )

        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)

    def test_check_and_notify_skips_non_feature_request(self):
        """Test that non-feature request messages don't trigger notification."""
        message = "What's my weight trend?"

        result = self.service.check_and_notify(
            user=self.user,
            message=message,
            intent_type='no_action',
        )

        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)

    @patch('apps.ai.feature_request_service.cache')
    def test_check_and_notify_rate_limited(self, mock_cache):
        """Test that repeated similar requests are rate limited."""
        message = "I wish I could track my sleep"

        # Simulate cache behavior
        cache_store = {}
        def get_side_effect(key, default=None):
            return cache_store.get(key, default)
        def set_side_effect(key, value, timeout=None):
            cache_store[key] = value

        mock_cache.get.side_effect = get_side_effect
        mock_cache.set.side_effect = set_side_effect

        # First call should send notification
        result1 = self.service.check_and_notify(
            user=self.user,
            message=message,
            intent_type='no_action',
        )
        self.assertTrue(result1)

        # Second call should be rate limited
        result2 = self.service.check_and_notify(
            user=self.user,
            message=message,
            intent_type='no_action',
        )
        self.assertFalse(result2)

        # Only one email should be sent
        self.assertEqual(len(mail.outbox), 1)


class FeatureRequestEdgeCaseTests(TestCase):
    """Edge case tests for feature request detection."""

    def setUp(self):
        self.service = FeatureRequestService()

    def test_case_insensitive_detection(self):
        """Test that detection is case insensitive."""
        messages = [
            "I WISH I COULD track my sleep",
            "i wish i could track my sleep",
            "I Wish I Could Track My Sleep",
        ]
        for message in messages:
            is_request, _ = self.service.detect_feature_request(message)
            self.assertTrue(is_request, f"Should detect: {message}")

    def test_empty_message(self):
        """Test handling of empty message."""
        is_request, pattern = self.service.detect_feature_request("")
        self.assertFalse(is_request)
        self.assertIsNone(pattern)

    def test_very_long_message(self):
        """Test handling of very long message."""
        # Long message with feature request buried in it
        message = "a " * 1000 + "I wish I could track my sleep" + " b" * 1000
        is_request, _ = self.service.detect_feature_request(message)
        self.assertTrue(is_request)

    def test_special_characters_in_message(self):
        """Test handling of special characters."""
        message = "I wish I could track my sleep!!! :) <script>alert('x')</script>"
        is_request, _ = self.service.detect_feature_request(message)
        self.assertTrue(is_request)


class FeatureRequestServiceSingletonTests(TestCase):
    """Tests for the singleton instance."""

    def test_singleton_exists(self):
        """Test that the singleton instance exists."""
        self.assertIsNotNone(feature_request_service)
        self.assertIsInstance(feature_request_service, FeatureRequestService)

    def test_singleton_methods_available(self):
        """Test that singleton has expected methods."""
        self.assertTrue(hasattr(feature_request_service, 'detect_feature_request'))
        self.assertTrue(hasattr(feature_request_service, 'check_and_notify'))
        self.assertTrue(hasattr(feature_request_service, 'should_notify'))
