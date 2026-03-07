# ==============================================================================
# File: test_proactive_briefing.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for v7 Proactive Daily Executive Briefing + v7.1 hardening
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-07
# ==============================================================================
"""
Proactive Briefing Tests (v7 + v7.1)

Tests cover:
1. Cooldown logic (timestamp-based, v7.1 Part 1)
2. Server-side idempotency (v7.1 Part 2)
3. No fake user message creation
4. Correct metadata (delivery_reason, generated_at)
5. View endpoint behavior
"""

from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.ai.models import AssistantConversation, AssistantMessage
from apps.ai.personal_assistant import PersonalAssistant, get_personal_assistant

User = get_user_model()


class ProactiveBriefingTestMixin:
    """Common setup for proactive briefing tests."""

    def create_user(self, email='briefing@example.com', password='testpass123'):
        user = User.objects.create_user(email=email, password=password)
        # Accept terms
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
        )
        # Complete onboarding
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def enable_ai(self, user):
        user.preferences.ai_enabled = True
        user.preferences.ai_data_consent = True
        user.preferences.ai_data_consent_date = timezone.now()
        user.preferences.personal_assistant_enabled = True
        user.preferences.personal_assistant_consent = True
        user.preferences.personal_assistant_consent_date = timezone.now()
        user.preferences.save()


class TestGenerateProactiveBriefing(ProactiveBriefingTestMixin, TestCase):
    """Test PersonalAssistant.generate_proactive_briefing() method."""

    def setUp(self):
        self.user = self.create_user()
        self.enable_ai(self.user)
        self.assistant = get_personal_assistant(self.user)

    @patch.object(PersonalAssistant, '_generate_response')
    def test_first_of_day_generates_briefing(self, mock_generate):
        """First call of the day should generate a briefing."""
        mock_generate.return_value = (
            "Danny — here's where things stand today.\n\n"
            "**Goals**\nYour current priority is improving health.\n\n"
            "**Recommendation**\nStart with your workout."
        )

        result = self.assistant.generate_proactive_briefing()

        self.assertIsNotNone(result)
        self.assertIn('response', result)
        self.assertIn('message_id', result)
        mock_generate.assert_called_once()

    @patch.object(PersonalAssistant, '_generate_response')
    def test_no_fake_user_message(self, mock_generate):
        """Briefing should NOT create a user message in conversation."""
        mock_generate.return_value = (
            "Danny — here's where things stand today. "
            "Your workout is not yet logged. Start there."
        )

        result = self.assistant.generate_proactive_briefing()
        self.assertIsNotNone(result)

        conversation = AssistantConversation.get_or_create_active(self.user)
        user_msgs = conversation.messages.filter(role='user').count()
        self.assertEqual(user_msgs, 0, "No fake user message should be created")

    @patch.object(PersonalAssistant, '_generate_response')
    def test_message_saved_as_proactive(self, mock_generate):
        """Briefing message should be saved with is_proactive=True."""
        mock_generate.return_value = (
            "Danny — here's where things stand today. "
            "No overdue tasks. Focus on your workout."
        )

        result = self.assistant.generate_proactive_briefing()
        msg = AssistantMessage.objects.get(id=result['message_id'])

        self.assertTrue(msg.is_proactive)
        self.assertEqual(msg.message_type, 'state_assessment')
        self.assertEqual(msg.role, 'assistant')

    @patch.object(PersonalAssistant, '_generate_response')
    def test_metadata_includes_delivery_reason(self, mock_generate):
        """v7.1: Metadata should include delivery_reason and generated_at."""
        mock_generate.return_value = (
            "Danny — here's where things stand today. "
            "No tasks due. Great day to focus on goals."
        )

        result = self.assistant.generate_proactive_briefing()
        msg = AssistantMessage.objects.get(id=result['message_id'])

        self.assertEqual(msg.metadata['check_in_type'], 'daily_executive_briefing')
        self.assertEqual(msg.metadata['delivery_reason'], 'first_open')
        self.assertIn('generated_at', msg.metadata)

    @patch.object(PersonalAssistant, '_generate_response')
    def test_cooldown_prevents_duplicate(self, mock_generate):
        """v7.1 Part 1: Second call within 4 hours returns None."""
        mock_generate.return_value = (
            "Danny — here's where things stand today. "
            "Your workout is pending. Get it done first."
        )

        # First call generates
        result1 = self.assistant.generate_proactive_briefing()
        self.assertIsNotNone(result1)

        # Second call should be blocked by cooldown
        result2 = self.assistant.generate_proactive_briefing()
        self.assertIsNone(result2)

        # _generate_response should only be called once
        self.assertEqual(mock_generate.call_count, 1)

    @patch.object(PersonalAssistant, '_generate_response')
    def test_idempotency_returns_existing(self, mock_generate):
        """v7.1 Part 2: Concurrent duplicate returns existing message."""
        mock_generate.return_value = (
            "Danny — here's where things stand today. "
            "Your plate is clear. Focus on health goals."
        )

        # First call generates
        result1 = self.assistant.generate_proactive_briefing()
        self.assertIsNotNone(result1)

        # Simulate concurrent request by clearing cooldown but keeping message
        conversation = AssistantConversation.get_or_create_active(self.user)
        metadata = conversation.metadata or {}
        metadata.pop('last_briefing_at', None)
        metadata.pop('last_briefing_date', None)
        conversation.metadata = metadata
        conversation.save(update_fields=['metadata'])

        # Second call should return existing message (idempotency check)
        result2 = self.assistant.generate_proactive_briefing()
        self.assertIsNotNone(result2)
        self.assertEqual(result2['message_id'], result1['message_id'])
        # _generate_response should still only be called once
        self.assertEqual(mock_generate.call_count, 1)

    @patch.object(PersonalAssistant, '_generate_response')
    def test_fallback_response_not_saved(self, mock_generate):
        """Fallback responses should not be saved as briefings."""
        mock_generate.return_value = "What do you need to get done?"

        result = self.assistant.generate_proactive_briefing()
        self.assertIsNone(result)

        # No proactive messages should be created
        conversation = AssistantConversation.get_or_create_active(self.user)
        proactive_count = conversation.messages.filter(
            is_proactive=True
        ).count()
        self.assertEqual(proactive_count, 0)

    @patch.object(PersonalAssistant, '_generate_response')
    def test_short_response_not_saved(self, mock_generate):
        """Very short responses (< 50 chars) should not be saved."""
        mock_generate.return_value = "Hi Danny."

        result = self.assistant.generate_proactive_briefing()
        self.assertIsNone(result)


class TestProactiveBriefingView(ProactiveBriefingTestMixin, TestCase):
    """Test the ProactiveBriefingView endpoint."""

    def setUp(self):
        self.user = self.create_user()
        self.enable_ai(self.user)
        self.client = Client()
        self.client.force_login(self.user)

    @patch.object(PersonalAssistant, '_generate_response')
    def test_post_returns_briefing(self, mock_generate):
        """POST /assistant/api/briefing/ returns briefing on first-of-day."""
        mock_generate.return_value = (
            "Danny — here's where things stand today. "
            "Your workout is pending. Start with that."
        )

        response = self.client.post(
            '/assistant/api/briefing/',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('response', data)
        self.assertTrue(data['is_proactive'])

    @patch.object(PersonalAssistant, '_generate_response')
    def test_post_returns_skipped_on_cooldown(self, mock_generate):
        """POST returns skipped: True when briefing already delivered."""
        mock_generate.return_value = (
            "Danny — here's where things stand today. "
            "No overdue items. Clean slate ahead."
        )

        # First call generates
        self.client.post(
            '/assistant/api/briefing/',
            content_type='application/json',
        )

        # Second call should be skipped
        response = self.client.post(
            '/assistant/api/briefing/',
            content_type='application/json',
        )

        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(data.get('skipped'))

    def test_unauthenticated_redirects(self):
        """Unauthenticated users should be redirected."""
        client = Client()  # Not logged in
        response = client.post(
            '/assistant/api/briefing/',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)

    def test_pa_disabled_returns_error(self):
        """Users without PA enabled should get an error."""
        self.user.preferences.personal_assistant_enabled = False
        self.user.preferences.save()

        response = self.client.post(
            '/assistant/api/briefing/',
            content_type='application/json',
        )

        data = response.json()
        self.assertFalse(data['success'])
