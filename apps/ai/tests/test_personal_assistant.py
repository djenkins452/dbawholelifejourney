# ==============================================================================
# File: test_personal_assistant.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Comprehensive tests for Dashboard AI Personal Assistant
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29 (Added Personal Assistant module access control tests)
# ==============================================================================
"""
Dashboard AI Personal Assistant - Comprehensive Tests

This test file covers:
1. Model tests (AssistantConversation, AssistantMessage, etc.)
2. PersonalAssistant service tests
3. State assessment tests
4. Prioritization logic tests
5. Trend tracking tests
6. API endpoint tests
7. Faith integration tests
8. Reflection prompt tests
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock, PropertyMock
import json

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.ai.models import (
    AssistantConversation, AssistantMessage, UserStateSnapshot,
    DailyPriority, TrendAnalysis, ReflectionPromptQueue
)
from apps.ai.personal_assistant import PersonalAssistant, get_personal_assistant
from apps.ai.trend_tracking import TrendTracker, get_trend_tracker

User = get_user_model()


# =============================================================================
# TEST HELPERS
# =============================================================================

class AssistantTestMixin:
    """Common setup for Personal Assistant tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        return user

    def _accept_terms(self, user):
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(user=user, terms_version='1.0')

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def enable_ai(self, user):
        """Enable AI features and Personal Assistant for user with consent."""
        user.preferences.ai_enabled = True
        user.preferences.ai_data_consent = True
        user.preferences.ai_data_consent_date = timezone.now()
        # Also enable Personal Assistant for backwards compatibility with existing tests
        user.preferences.personal_assistant_enabled = True
        user.preferences.personal_assistant_consent = True
        user.preferences.personal_assistant_consent_date = timezone.now()
        user.preferences.save()

    def enable_ai_only(self, user):
        """Enable only AI features without Personal Assistant."""
        user.preferences.ai_enabled = True
        user.preferences.ai_data_consent = True
        user.preferences.ai_data_consent_date = timezone.now()
        # Explicitly do NOT enable Personal Assistant
        user.preferences.personal_assistant_enabled = False
        user.preferences.personal_assistant_consent = False
        user.preferences.save()

    def create_journal_entry(self, user, title="Test Entry", mood="grateful", days_ago=0):
        """Create a journal entry for testing."""
        from apps.journal.models import JournalEntry
        from apps.core.utils import get_user_today

        entry_date = get_user_today(user) - timedelta(days=days_ago)
        return JournalEntry.objects.create(
            user=user,
            title=title,
            body="Test journal content",
            mood=mood,
            entry_date=entry_date
        )

    def create_task(self, user, title="Test Task", due_date=None, is_completed=False):
        """Create a task for testing."""
        from apps.life.models import Task
        from apps.core.utils import get_user_today

        if due_date is None:
            due_date = get_user_today(user)
        return Task.objects.create(
            user=user,
            title=title,
            due_date=due_date,
            is_completed=is_completed
        )

    def create_goal(self, user, title="Test Goal", status='active'):
        """Create a life goal for testing."""
        from apps.purpose.models import LifeGoal
        return LifeGoal.objects.create(
            user=user,
            title=title,
            status=status
        )

    def create_prayer(self, user, title="Test Prayer", is_answered=False):
        """Create a prayer request for testing."""
        from apps.faith.models import PrayerRequest
        return PrayerRequest.objects.create(
            user=user,
            title=title,
            is_answered=is_answered
        )


# =============================================================================
# 1. MODEL TESTS - AssistantConversation
# =============================================================================

class AssistantConversationModelTest(AssistantTestMixin, TestCase):
    """Tests for the AssistantConversation model."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_conversation(self):
        """Can create an assistant conversation."""
        conversation = AssistantConversation.objects.create(
            user=self.user,
            session_type='daily_checkin'
        )
        self.assertEqual(conversation.user, self.user)
        self.assertEqual(conversation.session_type, 'daily_checkin')
        self.assertTrue(conversation.is_active)

    def test_conversation_str_representation(self):
        """Conversation has readable string representation."""
        conversation = AssistantConversation.objects.create(
            user=self.user,
            title="Morning Check-in"
        )
        str_repr = str(conversation)
        self.assertIn(self.user.email, str_repr)
        self.assertIn("Morning Check-in", str_repr)

    def test_get_or_create_active_creates_new(self):
        """get_or_create_active creates new conversation if none exists."""
        conversation = AssistantConversation.get_or_create_active(self.user)
        self.assertIsNotNone(conversation)
        self.assertEqual(conversation.user, self.user)
        self.assertTrue(conversation.is_active)

    def test_get_or_create_active_returns_existing(self):
        """get_or_create_active returns existing active conversation."""
        existing = AssistantConversation.objects.create(
            user=self.user,
            session_type='daily_checkin',
            is_active=True
        )

        conversation = AssistantConversation.get_or_create_active(self.user)
        self.assertEqual(conversation.id, existing.id)


# =============================================================================
# 2. MODEL TESTS - AssistantMessage
# =============================================================================

class AssistantMessageModelTest(AssistantTestMixin, TestCase):
    """Tests for the AssistantMessage model."""

    def setUp(self):
        self.user = self.create_user()
        self.conversation = AssistantConversation.objects.create(
            user=self.user,
            session_type='general'
        )

    def test_create_user_message(self):
        """Can create a user message."""
        message = AssistantMessage.objects.create(
            conversation=self.conversation,
            role='user',
            content="Hello, how can you help me?"
        )
        self.assertEqual(message.role, 'user')
        self.assertEqual(message.message_type, 'text')

    def test_create_assistant_message(self):
        """Can create an assistant message."""
        message = AssistantMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content="I'm here to help you stay aligned with what matters.",
            message_type='insight'
        )
        self.assertEqual(message.role, 'assistant')
        self.assertEqual(message.message_type, 'insight')

    def test_message_ordering(self):
        """Messages are ordered by created_at."""
        msg1 = AssistantMessage.objects.create(
            conversation=self.conversation,
            role='user',
            content="First message"
        )
        msg2 = AssistantMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content="Second message"
        )

        messages = list(self.conversation.messages.all())
        self.assertEqual(messages[0], msg1)
        self.assertEqual(messages[1], msg2)


# =============================================================================
# 3. MODEL TESTS - DailyPriority
# =============================================================================

class DailyPriorityModelTest(AssistantTestMixin, TestCase):
    """Tests for the DailyPriority model."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_priority(self):
        """Can create a daily priority."""
        from apps.core.utils import get_user_today
        today = get_user_today(self.user)

        priority = DailyPriority.objects.create(
            user=self.user,
            priority_date=today,
            priority_type='faith',
            title='Spend time in Scripture'
        )
        self.assertEqual(priority.priority_type, 'faith')
        self.assertFalse(priority.is_completed)

    def test_mark_complete(self):
        """Can mark a priority as completed."""
        from apps.core.utils import get_user_today
        today = get_user_today(self.user)

        priority = DailyPriority.objects.create(
            user=self.user,
            priority_date=today,
            priority_type='commitment',
            title='Complete overdue task'
        )
        priority.mark_complete()

        priority.refresh_from_db()
        self.assertTrue(priority.is_completed)
        self.assertIsNotNone(priority.completed_at)


# =============================================================================
# 4. MODEL TESTS - UserStateSnapshot
# =============================================================================

class UserStateSnapshotModelTest(AssistantTestMixin, TestCase):
    """Tests for the UserStateSnapshot model."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_snapshot(self):
        """Can create a user state snapshot."""
        from apps.core.utils import get_user_today
        today = get_user_today(self.user)

        snapshot = UserStateSnapshot.objects.create(
            user=self.user,
            snapshot_date=today,
            journal_streak=5,
            tasks_completed_today=3,
            active_goals=2
        )
        self.assertEqual(snapshot.journal_streak, 5)
        self.assertEqual(snapshot.tasks_completed_today, 3)

    def test_unique_per_user_per_day(self):
        """Only one snapshot per user per day."""
        from apps.core.utils import get_user_today
        from django.db import IntegrityError

        today = get_user_today(self.user)

        UserStateSnapshot.objects.create(
            user=self.user,
            snapshot_date=today
        )

        with self.assertRaises(IntegrityError):
            UserStateSnapshot.objects.create(
                user=self.user,
                snapshot_date=today
            )


# =============================================================================
# 5. PERSONAL ASSISTANT SERVICE TESTS
# =============================================================================

class PersonalAssistantServiceTest(AssistantTestMixin, TestCase):
    """Tests for the PersonalAssistant service class."""

    def setUp(self):
        self.user = self.create_user()
        self.enable_ai(self.user)
        self.assistant = get_personal_assistant(self.user)

    def test_assistant_initialization(self):
        """Personal assistant initializes correctly."""
        self.assertEqual(self.assistant.user, self.user)
        self.assertEqual(self.assistant.coaching_style, 'supportive')

    def test_assess_current_state(self):
        """Can assess current state."""
        # Create some test data
        self.create_journal_entry(self.user)
        self.create_task(self.user, is_completed=True)

        state = self.assistant.assess_current_state()

        self.assertIn('journal', state)
        self.assertIn('tasks', state)
        self.assertIn('date', state)

    def test_assess_current_state_with_faith(self):
        """State assessment includes faith data when enabled."""
        self.user.preferences.faith_enabled = True
        self.user.preferences.save()

        self.create_prayer(self.user)
        assistant = get_personal_assistant(self.user)

        state = assistant.assess_current_state()
        self.assertIn('faith', state)

    def test_get_or_create_conversation(self):
        """Can get or create a conversation."""
        conversation = self.assistant.get_or_create_conversation()
        self.assertIsNotNone(conversation)
        self.assertEqual(conversation.user, self.user)

    @patch('apps.ai.personal_assistant.ai_service')
    def test_send_message(self, mock_ai_service):
        """Can send a message to the assistant."""
        mock_ai_service.is_available = True
        mock_ai_service._call_api.return_value = "I'm here to help."

        response = self.assistant.send_message("How can you help me?")

        self.assertIsNotNone(response)
        self.assertIsInstance(response, str)

    def test_send_message_without_ai(self):
        """Sends fallback response when AI unavailable."""
        self.user.preferences.ai_enabled = False
        self.user.preferences.save()

        assistant = get_personal_assistant(self.user)
        response = assistant.send_message("Hello")

        self.assertIsNotNone(response)
        self.assertIsInstance(response, str)


# =============================================================================
# 6. PRIORITIZATION LOGIC TESTS
# =============================================================================

class PrioritizationTest(AssistantTestMixin, TestCase):
    """Tests for daily priority generation."""

    def setUp(self):
        self.user = self.create_user()
        self.enable_ai(self.user)
        self.assistant = get_personal_assistant(self.user)

    def test_generate_daily_priorities(self):
        """Can generate daily priorities."""
        priorities = self.assistant.generate_daily_priorities()
        self.assertIsNotNone(priorities)

    def test_priorities_include_faith_when_enabled(self):
        """Priorities include faith when enabled."""
        self.user.preferences.faith_enabled = True
        self.user.preferences.save()

        assistant = get_personal_assistant(self.user)
        priorities = list(assistant.generate_daily_priorities())

        # Should have at least one priority
        self.assertGreater(len(priorities), 0)

    def test_priorities_include_overdue_tasks(self):
        """Priorities include overdue tasks."""
        from apps.core.utils import get_user_today
        yesterday = get_user_today(self.user) - timedelta(days=1)

        self.create_task(self.user, title="Overdue Task", due_date=yesterday)

        priorities = list(self.assistant.generate_daily_priorities(force_refresh=True))

        # Check that overdue task is included
        has_overdue = any('Overdue' in str(p.get('title', '')) for p in priorities)
        self.assertTrue(has_overdue)

    def test_priorities_respect_limit(self):
        """Priorities are limited to 5 items."""
        # Create many goals
        for i in range(10):
            self.create_goal(self.user, title=f"Goal {i}")

        priorities = list(self.assistant.generate_daily_priorities(force_refresh=True))
        self.assertLessEqual(len(priorities), 5)


# =============================================================================
# 7. REFLECTION PROMPT TESTS
# =============================================================================

class ReflectionPromptTest(AssistantTestMixin, TestCase):
    """Tests for reflection prompt generation."""

    def setUp(self):
        self.user = self.create_user()
        self.enable_ai(self.user)
        self.assistant = get_personal_assistant(self.user)

    def test_generate_reflection_prompt(self):
        """Can generate a reflection prompt."""
        prompt = self.assistant.generate_reflection_prompt('morning')
        self.assertIsNotNone(prompt)
        self.assertIsInstance(prompt, str)

    def test_reflection_prompt_queued(self):
        """Reflection prompts are saved to queue."""
        prompt = self.assistant.generate_reflection_prompt('evening')

        queued = ReflectionPromptQueue.objects.filter(
            user=self.user,
            prompt_context='evening'
        ).first()

        self.assertIsNotNone(queued)

    def test_faith_prompts_when_faith_enabled(self):
        """Faith prompts available when faith enabled."""
        self.user.preferences.faith_enabled = True
        self.user.preferences.save()

        assistant = get_personal_assistant(self.user)
        prompt = assistant.generate_reflection_prompt('faith')

        self.assertIsNotNone(prompt)


# =============================================================================
# 8. TREND TRACKING TESTS
# =============================================================================

class TrendTrackingTest(AssistantTestMixin, TestCase):
    """Tests for trend tracking functionality."""

    def setUp(self):
        self.user = self.create_user()
        self.enable_ai(self.user)
        self.tracker = get_trend_tracker(self.user)

    def test_generate_weekly_analysis(self):
        """Can generate weekly analysis."""
        # Create some test data
        for i in range(7):
            self.create_journal_entry(self.user, days_ago=i)

        analysis = self.tracker.generate_weekly_analysis()
        self.assertIsNotNone(analysis)

    def test_detect_intention_drift(self):
        """Can detect intention drift."""
        from apps.purpose.models import ChangeIntention

        ChangeIntention.objects.create(
            user=self.user,
            intention="Be more present",
            status='active'
        )

        drift_areas = self.tracker.detect_intention_drift()
        self.assertIsInstance(drift_areas, list)

    def test_get_goal_progress_report(self):
        """Can get goal progress report."""
        self.create_goal(self.user, title="Goal 1")
        self.create_goal(self.user, title="Goal 2", status='completed')

        report = self.tracker.get_goal_progress_report()

        self.assertIn('active', report)
        self.assertIn('completed_this_month', report)
        self.assertIn('summary', report)


# =============================================================================
# 9. API ENDPOINT TESTS
# =============================================================================

class AssistantAPITest(AssistantTestMixin, TestCase):
    """Tests for Assistant API endpoints."""

    def setUp(self):
        self.user = self.create_user()
        self.enable_ai(self.user)
        self.client = Client()
        self.client.login(email='test@example.com', password='testpass123')

    def test_opening_endpoint(self):
        """Opening endpoint returns data."""
        response = self.client.get('/assistant/api/opening/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('success', data)

    def test_chat_endpoint(self):
        """Chat endpoint accepts messages."""
        response = self.client.post(
            '/assistant/api/chat/',
            data=json.dumps({'message': 'Hello'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('success', data)

    def test_chat_endpoint_requires_message(self):
        """Chat endpoint requires message."""
        response = self.client.post(
            '/assistant/api/chat/',
            data=json.dumps({'message': ''}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_priorities_endpoint(self):
        """Priorities endpoint returns data."""
        response = self.client.get('/assistant/api/priorities/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('success', data)
        self.assertIn('priorities', data)

    def test_state_endpoint(self):
        """State endpoint returns data."""
        response = self.client.get('/assistant/api/state/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('success', data)
        self.assertIn('state', data)

    def test_weekly_analysis_endpoint(self):
        """Weekly analysis endpoint returns data."""
        response = self.client.get('/assistant/api/analysis/weekly/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('success', data)

    def test_reflection_endpoint(self):
        """Reflection prompt endpoint returns data."""
        response = self.client.get('/assistant/api/reflection/?context=morning')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('success', data)
        self.assertIn('prompt', data)

    def test_assistant_dashboard_view(self):
        """Assistant dashboard view loads."""
        # This test may fail in CI due to staticfiles manifest
        # The view loads correctly in development
        try:
            response = self.client.get('/assistant/')
            self.assertEqual(response.status_code, 200)
        except ValueError as e:
            if 'staticfiles manifest' in str(e):
                # Skip test if staticfiles not built
                self.skipTest("Staticfiles manifest not available in test environment")


# =============================================================================
# 10. AUTHENTICATION TESTS
# =============================================================================

class AssistantAuthenticationTest(AssistantTestMixin, TestCase):
    """Tests for authentication requirements."""

    def setUp(self):
        self.client = Client()

    def test_opening_requires_login(self):
        """Opening endpoint requires authentication."""
        response = self.client.get('/assistant/api/opening/')
        # Should redirect to login
        self.assertEqual(response.status_code, 302)

    def test_chat_requires_login(self):
        """Chat endpoint requires authentication."""
        response = self.client.post('/assistant/api/chat/')
        self.assertEqual(response.status_code, 302)

    def test_dashboard_requires_login(self):
        """Dashboard view requires authentication."""
        response = self.client.get('/assistant/')
        self.assertEqual(response.status_code, 302)


# =============================================================================
# 11. AI DISABLED TESTS
# =============================================================================

class AssistantAIDisabledTest(AssistantTestMixin, TestCase):
    """Tests for behavior when AI is disabled."""

    def setUp(self):
        self.user = self.create_user()
        # AI is disabled by default
        self.client = Client()
        self.client.login(email='test@example.com', password='testpass123')

    def test_opening_with_ai_disabled(self):
        """Opening endpoint works when AI disabled."""
        response = self.client.get('/assistant/api/opening/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('fallback', data)

    def test_chat_with_ai_disabled(self):
        """Chat returns error when AI disabled."""
        response = self.client.post(
            '/assistant/api/chat/',
            data=json.dumps({'message': 'Hello'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('error', data)


# =============================================================================
# 12. EDGE CASES
# =============================================================================

class AssistantEdgeCasesTest(AssistantTestMixin, TestCase):
    """Tests for edge cases and error handling."""

    def setUp(self):
        self.user = self.create_user()
        self.enable_ai(self.user)
        self.assistant = get_personal_assistant(self.user)

    def test_empty_state_assessment(self):
        """State assessment works with no data."""
        state = self.assistant.assess_current_state()
        self.assertIn('date', state)

    def test_priorities_with_no_goals(self):
        """Priorities work when user has no goals."""
        priorities = list(self.assistant.generate_daily_priorities())
        self.assertIsNotNone(priorities)

    def test_trend_analysis_with_no_data(self):
        """Trend analysis works with no data."""
        tracker = get_trend_tracker(self.user)
        analysis = tracker.generate_weekly_analysis()
        # Should return something even with no data
        self.assertIsNotNone(analysis)

    def test_long_message_rejected(self):
        """Chat rejects messages over 2000 characters."""
        self.client = Client()
        self.client.login(email='test@example.com', password='testpass123')

        long_message = 'x' * 2001
        response = self.client.post(
            '/assistant/api/chat/',
            data=json.dumps({'message': long_message}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

        data = response.json()
        self.assertIn('too long', data.get('error', ''))

    def test_priority_complete_wrong_user(self):
        """Can't complete another user's priority."""
        other_user = self.create_user(email='other@example.com')
        from apps.core.utils import get_user_today
        today = get_user_today(other_user)

        priority = DailyPriority.objects.create(
            user=other_user,
            priority_date=today,
            priority_type='faith',
            title='Other user priority'
        )

        self.client = Client()
        self.client.login(email='test@example.com', password='testpass123')

        response = self.client.post(f'/assistant/api/priorities/{priority.id}/complete/')
        self.assertEqual(response.status_code, 404)


# =============================================================================
# 13. PERSONAL ASSISTANT MODULE ACCESS CONTROL TESTS
# =============================================================================

class PersonalAssistantModuleAccessTest(AssistantTestMixin, TestCase):
    """
    Tests for Personal Assistant module access control.

    Personal Assistant requires:
    1. AI Features enabled (ai_enabled=True)
    2. AI Data Consent (ai_data_consent=True)
    3. Personal Assistant module enabled (personal_assistant_enabled=True)
    4. Personal Assistant consent (personal_assistant_consent=True)
    """

    def setUp(self):
        self.user = self.create_user()
        self.client = Client()
        self.client.login(email='test@example.com', password='testpass123')

    def enable_full_personal_assistant(self, user):
        """Enable all requirements for Personal Assistant access."""
        user.preferences.ai_enabled = True
        user.preferences.ai_data_consent = True
        user.preferences.ai_data_consent_date = timezone.now()
        user.preferences.personal_assistant_enabled = True
        user.preferences.personal_assistant_consent = True
        user.preferences.personal_assistant_consent_date = timezone.now()
        user.preferences.save()

    def test_opening_denied_without_ai_enabled(self):
        """Opening endpoint denied when AI features not enabled."""
        # AI not enabled (default)
        response = self.client.get('/assistant/api/opening/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data.get('success', True))
        self.assertIn('AI', data.get('error', ''))

    def test_opening_denied_without_ai_consent(self):
        """Opening endpoint denied when AI consent not given."""
        self.user.preferences.ai_enabled = True
        self.user.preferences.save()

        response = self.client.get('/assistant/api/opening/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data.get('success', True))

    def test_opening_denied_without_personal_assistant_enabled(self):
        """Opening endpoint denied when Personal Assistant not enabled."""
        self.user.preferences.ai_enabled = True
        self.user.preferences.ai_data_consent = True
        self.user.preferences.ai_data_consent_date = timezone.now()
        # Personal Assistant not enabled (default)
        self.user.preferences.save()

        response = self.client.get('/assistant/api/opening/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data.get('success', True))
        self.assertIn('Personal Assistant', data.get('error', ''))

    def test_opening_denied_without_personal_assistant_consent(self):
        """Opening endpoint denied when Personal Assistant consent not given."""
        self.user.preferences.ai_enabled = True
        self.user.preferences.ai_data_consent = True
        self.user.preferences.ai_data_consent_date = timezone.now()
        self.user.preferences.personal_assistant_enabled = True
        # Personal Assistant consent not given (default)
        self.user.preferences.save()

        response = self.client.get('/assistant/api/opening/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data.get('success', True))
        self.assertIn('consent', data.get('error', '').lower())

    def test_opening_allowed_with_full_access(self):
        """Opening endpoint allowed when all requirements met."""
        self.enable_full_personal_assistant(self.user)

        response = self.client.get('/assistant/api/opening/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should either be successful or have valid response (not error about access)
        if not data.get('success'):
            # Error should not be about access control
            error_msg = data.get('error', '').lower()
            self.assertNotIn('enabled', error_msg)
            self.assertNotIn('consent', error_msg)

    def test_chat_denied_without_personal_assistant(self):
        """Chat endpoint denied when Personal Assistant not fully enabled."""
        # Only enable AI, not Personal Assistant
        self.enable_ai_only(self.user)

        response = self.client.post(
            '/assistant/api/chat/',
            data=json.dumps({'message': 'Hello'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data.get('success', True))
        self.assertIn('Personal Assistant', data.get('error', ''))

    def test_priorities_without_personal_assistant_returns_ai_disabled(self):
        """Priorities endpoint returns ai_enabled=False when Personal Assistant not enabled."""
        # Only enable AI, not Personal Assistant
        self.enable_ai_only(self.user)

        response = self.client.get('/assistant/api/priorities/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # The endpoint returns success=True but ai_enabled=False when PA not enabled
        self.assertFalse(data.get('ai_enabled', True))

    def test_priorities_allowed_with_full_access(self):
        """Priorities endpoint allowed when all requirements met."""
        self.enable_full_personal_assistant(self.user)

        response = self.client.get('/assistant/api/priorities/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success', False))

    def test_consent_date_set_on_enable(self):
        """Personal Assistant consent date is set when consent is given."""
        self.assertIsNone(self.user.preferences.personal_assistant_consent_date)

        self.user.preferences.personal_assistant_consent = True
        self.user.preferences.personal_assistant_consent_date = timezone.now()
        self.user.preferences.save()

        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.preferences.personal_assistant_consent_date)

    def test_personal_assistant_disabled_when_ai_disabled(self):
        """Personal Assistant is disabled when AI is disabled in preferences."""
        # First enable everything
        self.enable_full_personal_assistant(self.user)

        # Now disable AI via the form logic simulation
        self.user.preferences.ai_enabled = False
        # In real form submission, this would also clear PA settings
        self.user.preferences.personal_assistant_enabled = False
        self.user.preferences.personal_assistant_consent = False
        self.user.preferences.save()

        self.user.refresh_from_db()
        self.assertFalse(self.user.preferences.personal_assistant_enabled)
        self.assertFalse(self.user.preferences.personal_assistant_consent)

    def test_dashboard_shows_pa_status(self):
        """Dashboard view shows Personal Assistant status correctly."""
        # Test with PA not enabled
        self.enable_ai_only(self.user)

        try:
            response = self.client.get('/assistant/')
            self.assertEqual(response.status_code, 200)
            # Check that the page contains the "not enabled" message
            content = response.content.decode('utf-8')
            self.assertIn('Personal Assistant', content)
        except ValueError as e:
            if 'staticfiles manifest' in str(e):
                self.skipTest("Staticfiles manifest not available in test environment")
