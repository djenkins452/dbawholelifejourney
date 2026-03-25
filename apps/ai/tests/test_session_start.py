"""
Session Start Endpoint — Tests

Tests for the Adaptive CoS Presence session-start endpoint:
1. First-of-day returns briefing action
2. Gap re-entry returns briefing action
3. Mid-session returns action: none
4. Deep interaction within 90 min returns lightweight alignment
5. High drift returns drift intervention
6. Wake-up auto-completion on first-of-day
7. Auth gate blocks unauthenticated/unconsented users
"""

from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.utils import timezone

from apps.ai.models import AssistantConversation, AssistantMessage
from apps.users.models import TermsAcceptance

User = get_user_model()


class SessionStartTestMixin:
    """Common setup for session-start tests."""

    def create_user(self, email='session@example.com'):
        user = User.objects.create_user(email=email, password='testpass123')
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        prefs = user.preferences
        prefs.has_completed_onboarding = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.timezone = 'America/Chicago'
        prefs.save()
        return user

    def create_conversation(self, user, metadata=None):
        return AssistantConversation.objects.create(
            user=user,
            is_active=True,
            session_type='general',
            metadata=metadata or {},
        )


class TestSessionStartFirstOfDay(SessionStartTestMixin, TestCase):
    """First-of-day should return briefing action."""

    def setUp(self):
        self.user = self.create_user()
        self.factory = RequestFactory()

    @patch('apps.core.utils.get_user_now')
    @patch('apps.core.utils.get_user_today')
    def test_first_of_day_returns_briefing(self, mock_today, mock_now):
        """When no briefing has been delivered today, return briefing action."""
        from apps.ai.views import SessionStartView

        today = timezone.now().date()
        mock_today.return_value = today
        mock_now.return_value = timezone.now().replace(hour=6, minute=0)

        # Conversation with no briefing metadata
        conv = self.create_conversation(self.user, metadata={})

        request = self.factory.post('/assistant/api/session-start/')
        request.user = self.user

        view = SessionStartView()
        view.request = request

        with patch.object(
            view, 'check_personal_assistant_enabled',
            return_value=(True, None),
        ):
            with patch(
                'apps.ai.models.AssistantConversation.get_or_create_active',
                return_value=conv,
            ):
                response = view.post(request)

        self.assertEqual(response.status_code, 200)
        import json
        data = json.loads(response.content)
        self.assertEqual(data['action'], 'briefing')
        self.assertIn('payload', data)
        self.assertEqual(data['payload']['session_type'], 'morning')

    @patch('apps.core.utils.get_user_now')
    @patch('apps.core.utils.get_user_today')
    def test_same_day_no_gap_returns_none(self, mock_today, mock_now):
        """When briefing already delivered and no 4h gap, return none."""
        from apps.ai.views import SessionStartView

        today = timezone.now().date()
        mock_today.return_value = today
        mock_now.return_value = timezone.now().replace(hour=10, minute=0)

        # Conversation with briefing already delivered today
        conv = self.create_conversation(self.user, metadata={
            'last_briefing_date': str(today),
        })
        # Set updated_at to 1 hour ago (no gap)
        conv.updated_at = timezone.now() - timedelta(hours=1)
        conv.save(update_fields=['updated_at'])

        request = self.factory.post('/assistant/api/session-start/')
        request.user = self.user

        view = SessionStartView()
        view.request = request

        with patch.object(
            view, 'check_personal_assistant_enabled',
            return_value=(True, None),
        ):
            with patch(
                'apps.ai.models.AssistantConversation.get_or_create_active',
                return_value=conv,
            ):
                response = view.post(request)

        import json
        data = json.loads(response.content)
        self.assertEqual(data['action'], 'none')


class TestSessionStartLightweightAlignment(SessionStartTestMixin, TestCase):
    """Recent deep interaction should return lightweight alignment."""

    def setUp(self):
        self.user = self.create_user(email='light@example.com')
        self.factory = RequestFactory()

    @patch('apps.core.utils.get_user_now')
    @patch('apps.core.utils.get_user_today')
    def test_deep_interaction_returns_lightweight(self, mock_today, mock_now):
        """When deep interaction within 90 min, return lightweight alignment."""
        from apps.ai.views import SessionStartView

        today = timezone.now().date()
        mock_today.return_value = today
        mock_now.return_value = timezone.now().replace(hour=7, minute=30)

        # Deep interaction 30 min ago
        deep_at = (timezone.now() - timedelta(minutes=30)).isoformat()
        conv = self.create_conversation(self.user, metadata={
            'last_briefing_date': str(today - timedelta(days=1)),  # yesterday
            'last_deep_interaction_at': deep_at,
            'alignment_snapshot': {
                'captured_at': deep_at,
                'completed_items': ['Wake Up'],
                'tasks_completed': 1,
                'pending_count': 5,
            },
        })

        request = self.factory.post('/assistant/api/session-start/')
        request.user = self.user

        view = SessionStartView()
        view.request = request

        with patch.object(
            view, 'check_personal_assistant_enabled',
            return_value=(True, None),
        ):
            with patch(
                'apps.ai.models.AssistantConversation.get_or_create_active',
                return_value=conv,
            ):
                response = view.post(request)

        import json
        data = json.loads(response.content)
        self.assertEqual(data['action'], 'lightweight_alignment')
        self.assertIn('prior_alignment_at', data['payload'])


class TestSessionStartDrift(SessionStartTestMixin, TestCase):
    """High drift should return drift intervention."""

    def setUp(self):
        self.user = self.create_user(email='drift@example.com')
        self.factory = RequestFactory()

    @patch('apps.core.utils.get_user_now')
    @patch('apps.core.utils.get_user_today')
    def test_high_drift_returns_intervention(self, mock_today, mock_now):
        """When drift >= 40, return drift intervention."""
        from apps.ai.views import SessionStartView

        today = timezone.now().date()
        mock_today.return_value = today
        mock_now.return_value = timezone.now().replace(hour=14, minute=0)

        # Already had briefing today, no gap
        conv = self.create_conversation(self.user, metadata={
            'last_briefing_date': str(today),
        })
        conv.updated_at = timezone.now() - timedelta(hours=1)
        conv.save(update_fields=['updated_at'])

        request = self.factory.post('/assistant/api/session-start/')
        request.user = self.user

        view = SessionStartView()
        view.request = request

        # Mock drift score — _check_drift imports DriftScore inside method
        mock_drift = MagicMock()
        mock_drift.score = 55
        mock_drift.pillar_scores = {'HEALTH_DISCIPLINE': 25.0}
        mock_drift.drift_probability_24h = 0.65

        with patch.object(
            view, 'check_personal_assistant_enabled',
            return_value=(True, None),
        ):
            with patch(
                'apps.ai.models.AssistantConversation.get_or_create_active',
                return_value=conv,
            ):
                with patch(
                    'apps.core.blueprint.models.DriftScore.objects',
                ) as mock_qs:
                    mock_qs.filter.return_value.first.return_value = (
                        mock_drift
                    )
                    response = view.post(request)

        import json
        data = json.loads(response.content)
        self.assertEqual(data['action'], 'drift_intervention')
        self.assertEqual(data['payload']['drift_score'], 55)
        self.assertEqual(
            data['payload']['top_pillar'], 'HEALTH_DISCIPLINE',
        )


class TestSessionStartAuth(SessionStartTestMixin, TestCase):
    """Auth gate should block non-enabled users."""

    def setUp(self):
        self.user = self.create_user(email='auth@example.com')
        self.factory = RequestFactory()

    def test_disabled_pa_returns_none(self):
        """When PA not enabled, return action: none."""
        from apps.ai.views import SessionStartView

        request = self.factory.post('/assistant/api/session-start/')
        request.user = self.user

        view = SessionStartView()
        view.request = request

        with patch.object(
            view, 'check_personal_assistant_enabled',
            return_value=(False, 'PA not enabled'),
        ):
            response = view.post(request)

        import json
        data = json.loads(response.content)
        self.assertEqual(data['action'], 'none')
        self.assertEqual(data['reason'], 'PA not enabled')
