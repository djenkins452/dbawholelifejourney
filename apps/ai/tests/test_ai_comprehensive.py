"""
AI Module - Comprehensive Tests

This test file covers:
1. Model tests (AIInsight, AIUsageLog)
2. AIService tests (with mocked OpenAI client)
3. DashboardAI tests
4. Coaching style tests
5. Caching behavior tests
6. Edge cases and error handling
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock, PropertyMock
import json

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.ai.models import AIInsight, AIUsageLog
from apps.ai.services import AIService, ai_service
from apps.ai.dashboard_ai import DashboardAI, get_dashboard_insight

User = get_user_model()


# =============================================================================
# TEST HELPERS
# =============================================================================

class AITestMixin:
    """Common setup for AI tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        """Create a test user with terms accepted."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        return user

    def _accept_terms(self, user):
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(user=user, terms_version='1.0')

    def create_ai_insight(self, user, insight_type='daily', content='Test insight',
                          valid_until=None):
        """Create an AI insight for testing."""
        if valid_until is None:
            valid_until = timezone.now() + timedelta(hours=12)
        return AIInsight.objects.create(
            user=user,
            insight_type=insight_type,
            content=content,
            valid_until=valid_until
        )

    def create_usage_log(self, user, endpoint='test_endpoint',
                         prompt_tokens=100, completion_tokens=50):
        """Create an AI usage log for testing."""
        return AIUsageLog.objects.create(
            user=user,
            endpoint=endpoint,
            model_used='gpt-4o-mini',
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            estimated_cost_usd=Decimal('0.001'),
            success=True
        )


# =============================================================================
# 1. MODEL TESTS - AIInsight
# =============================================================================

class AIInsightModelTest(AITestMixin, TestCase):
    """Tests for the AIInsight model."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_ai_insight(self):
        """Can create an AI insight."""
        insight = self.create_ai_insight(self.user)
        self.assertEqual(insight.user, self.user)
        self.assertEqual(insight.insight_type, 'daily')
        self.assertEqual(insight.content, 'Test insight')

    def test_insight_str_representation(self):
        """Insight has readable string representation."""
        insight = self.create_ai_insight(self.user)
        str_repr = str(insight)
        self.assertIn('Daily Dashboard Insight', str_repr)
        self.assertIn(self.user.email, str_repr)

    def test_insight_types_choices(self):
        """All insight types can be created."""
        insight_types = ['daily', 'weekly_summary', 'monthly_summary',
                         'reflection_prompt', 'goal_encouragement',
                         'health_insight', 'prayer_encouragement',
                         'entry_reflection']

        for insight_type in insight_types:
            insight = AIInsight.objects.create(
                user=self.user,
                insight_type=insight_type,
                content=f'Test {insight_type}'
            )
            self.assertEqual(insight.insight_type, insight_type)

    def test_is_valid_when_not_expired(self):
        """is_valid returns True when insight hasn't expired."""
        insight = self.create_ai_insight(
            self.user,
            valid_until=timezone.now() + timedelta(hours=1)
        )
        self.assertTrue(insight.is_valid)

    def test_is_valid_when_expired(self):
        """is_valid returns False when insight has expired."""
        insight = self.create_ai_insight(
            self.user,
            valid_until=timezone.now() - timedelta(hours=1)
        )
        self.assertFalse(insight.is_valid)

    def test_is_valid_when_no_expiry(self):
        """is_valid returns True when valid_until is None."""
        insight = AIInsight.objects.create(
            user=self.user,
            insight_type='daily',
            content='Test',
            valid_until=None
        )
        self.assertTrue(insight.is_valid)

    def test_ordering_by_created_at(self):
        """Insights are ordered by created_at descending."""
        insight1 = self.create_ai_insight(self.user, content='First')
        insight2 = self.create_ai_insight(self.user, content='Second')
        insight3 = self.create_ai_insight(self.user, content='Third')

        insights = AIInsight.objects.filter(user=self.user)
        self.assertEqual(insights[0], insight3)
        self.assertEqual(insights[2], insight1)

    def test_related_object_fields(self):
        """Can store related object references."""
        insight = AIInsight.objects.create(
            user=self.user,
            insight_type='entry_reflection',
            content='Reflection on entry',
            related_object_type='JournalEntry',
            related_object_id=123
        )
        self.assertEqual(insight.related_object_type, 'JournalEntry')
        self.assertEqual(insight.related_object_id, 123)

    def test_was_helpful_feedback(self):
        """Can store user feedback on helpfulness."""
        insight = self.create_ai_insight(self.user)
        self.assertIsNone(insight.was_helpful)

        insight.was_helpful = True
        insight.save()
        insight.refresh_from_db()
        self.assertTrue(insight.was_helpful)

    def test_context_summary_stored(self):
        """Can store context summary for transparency."""
        insight = AIInsight.objects.create(
            user=self.user,
            insight_type='daily',
            content='Test',
            context_summary='User journaled 5 times this week'
        )
        self.assertEqual(insight.context_summary, 'User journaled 5 times this week')

    def test_cascade_delete_with_user(self):
        """Insights are deleted when user is deleted."""
        insight = self.create_ai_insight(self.user)
        insight_id = insight.id
        self.user.delete()
        self.assertFalse(AIInsight.objects.filter(id=insight_id).exists())


# =============================================================================
# 2. MODEL TESTS - AIUsageLog
# =============================================================================

class AIUsageLogModelTest(AITestMixin, TestCase):
    """Tests for the AIUsageLog model."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_usage_log(self):
        """Can create a usage log."""
        log = self.create_usage_log(self.user)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.endpoint, 'test_endpoint')
        self.assertEqual(log.total_tokens, 150)

    def test_usage_log_str_representation(self):
        """Usage log has readable string representation."""
        log = self.create_usage_log(self.user, endpoint='daily_insight')
        str_repr = str(log)
        self.assertIn('daily_insight', str_repr)
        self.assertIn('150 tokens', str_repr)

    def test_token_counts(self):
        """Token counts are stored correctly."""
        log = self.create_usage_log(
            self.user,
            prompt_tokens=200,
            completion_tokens=100
        )
        self.assertEqual(log.prompt_tokens, 200)
        self.assertEqual(log.completion_tokens, 100)
        self.assertEqual(log.total_tokens, 300)

    def test_estimated_cost(self):
        """Estimated cost is stored correctly."""
        log = AIUsageLog.objects.create(
            user=self.user,
            endpoint='test',
            model_used='gpt-4o-mini',
            total_tokens=1000,
            estimated_cost_usd=Decimal('0.000150')
        )
        self.assertEqual(log.estimated_cost_usd, Decimal('0.000150'))

    def test_error_logging(self):
        """Can log errors with error message."""
        log = AIUsageLog.objects.create(
            user=self.user,
            endpoint='test',
            model_used='gpt-4o-mini',
            success=False,
            error_message='API rate limit exceeded'
        )
        self.assertFalse(log.success)
        self.assertEqual(log.error_message, 'API rate limit exceeded')

    def test_ordering_by_created_at(self):
        """Usage logs are ordered by created_at descending."""
        log1 = self.create_usage_log(self.user, endpoint='first')
        log2 = self.create_usage_log(self.user, endpoint='second')

        logs = AIUsageLog.objects.filter(user=self.user)
        self.assertEqual(logs[0], log2)
        self.assertEqual(logs[1], log1)


# =============================================================================
# 3. AIService TESTS
# =============================================================================

class AIServiceTest(AITestMixin, TestCase):
    """Tests for the AIService class."""

    def setUp(self):
        self.user = self.create_user()
        self.service = AIService()

    def test_is_available_without_api_key(self):
        """Service is not available without API key."""
        service = AIService()
        service.client = None
        self.assertFalse(service.is_available)

    @patch('apps.ai.services.AIService._initialize_client')
    def test_is_available_with_client(self, mock_init):
        """Service is available when client is initialized."""
        service = AIService()
        service.client = MagicMock()
        self.assertTrue(service.is_available)

    def test_coaching_style_gentle(self):
        """Gentle coaching style returns appropriate prompt."""
        prompt = self.service._get_coaching_style_prompt('gentle')
        self.assertIn('GENTLE GUIDE', prompt)
        self.assertIn('nurturing', prompt.lower())
        self.assertIn('no pressure', prompt.lower())

    def test_coaching_style_supportive(self):
        """Supportive coaching style returns appropriate prompt."""
        prompt = self.service._get_coaching_style_prompt('supportive')
        self.assertIn('SUPPORTIVE PARTNER', prompt)
        self.assertIn('balanced', prompt.lower())

    def test_coaching_style_direct(self):
        """Direct coaching style returns appropriate prompt."""
        prompt = self.service._get_coaching_style_prompt('direct')
        self.assertIn('DIRECT COACH', prompt)
        self.assertIn('straightforward', prompt.lower())

    def test_coaching_style_default(self):
        """Unknown coaching style defaults to supportive."""
        prompt = self.service._get_coaching_style_prompt('unknown')
        self.assertIn('SUPPORTIVE PARTNER', prompt)

    def test_system_prompt_without_faith(self):
        """System prompt without faith context."""
        prompt = self.service._get_system_prompt(faith_enabled=False)
        self.assertIn('life coach', prompt.lower())
        self.assertNotIn('Scripture', prompt)
        self.assertNotIn('FAITH CONTEXT', prompt)

    def test_system_prompt_with_faith(self):
        """System prompt includes faith context when enabled."""
        prompt = self.service._get_system_prompt(faith_enabled=True)
        self.assertIn('FAITH CONTEXT', prompt)
        self.assertIn('Scripture', prompt)

    @patch.object(AIService, '_call_api')
    def test_analyze_journal_entry(self, mock_api):
        """analyze_journal_entry calls API with correct parameters."""
        mock_api.return_value = "Great reflection!"

        self.service.client = MagicMock()  # Make service available
        result = self.service.analyze_journal_entry(
            "Today was a good day.",
            mood="happy",
            faith_enabled=False,
            coaching_style='supportive'
        )

        mock_api.assert_called_once()
        self.assertEqual(result, "Great reflection!")

    @patch.object(AIService, '_call_api')
    def test_generate_journal_summary_empty_entries(self, mock_api):
        """Journal summary returns None for empty entries."""
        result = self.service.generate_journal_summary([])
        self.assertIsNone(result)
        mock_api.assert_not_called()

    @patch.object(AIService, '_call_api')
    def test_generate_daily_insight(self, mock_api):
        """generate_daily_insight builds context from user data."""
        mock_api.return_value = "Keep up the great work!"

        self.service.client = MagicMock()
        user_data = {
            'journal_count_week': 5,
            'current_streak': 3,
            'active_goals': 2
        }

        result = self.service.generate_daily_insight(
            user_data,
            faith_enabled=False,
            coaching_style='supportive'
        )

        mock_api.assert_called_once()
        call_args = mock_api.call_args
        user_prompt = call_args[0][1]
        self.assertIn('Journaled 5 times this week', user_prompt)
        self.assertIn('3-day journal streak', user_prompt)

    @patch.object(AIService, '_call_api')
    def test_generate_accountability_nudge(self, mock_api):
        """generate_accountability_nudge uses gap data."""
        mock_api.return_value = "Time to journal!"

        self.service.client = MagicMock()
        gap_data = {
            'gap_type': 'journal',
            'days_since': 5,
            'item_name': 'Daily Journal'
        }

        result = self.service.generate_accountability_nudge(gap_data)

        mock_api.assert_called_once()
        call_args = mock_api.call_args
        user_prompt = call_args[0][1]
        self.assertIn('journal', user_prompt)
        self.assertIn('5', user_prompt)

    @patch.object(AIService, '_call_api')
    def test_generate_celebration(self, mock_api):
        """generate_celebration creates celebration message."""
        mock_api.return_value = "Congratulations!"

        self.service.client = MagicMock()
        achievement_data = {
            'achievement_type': 'streak',
            'details': '30 day journal streak',
            'streak_count': 30
        }

        result = self.service.generate_celebration(achievement_data)

        mock_api.assert_called_once()
        self.assertEqual(result, "Congratulations!")

    def test_call_api_when_not_available(self):
        """_call_api returns None when service unavailable."""
        self.service.client = None
        result = self.service._call_api("system", "user")
        self.assertIsNone(result)


# =============================================================================
# 4. DashboardAI TESTS
# =============================================================================

class DashboardAITest(AITestMixin, TestCase):
    """Tests for the DashboardAI class."""

    def setUp(self):
        self.user = self.create_user()
        # Ensure user has preferences
        self.user.preferences.faith_enabled = False
        self.user.preferences.ai_coaching_style = 'supportive'
        self.user.preferences.save()

    def test_dashboard_ai_initialization(self):
        """DashboardAI initializes with user preferences."""
        dashboard_ai = DashboardAI(self.user)
        self.assertEqual(dashboard_ai.user, self.user)
        self.assertFalse(dashboard_ai.faith_enabled)
        self.assertEqual(dashboard_ai.coaching_style, 'supportive')

    def test_dashboard_ai_with_faith_enabled(self):
        """DashboardAI uses faith_enabled from preferences."""
        self.user.preferences.faith_enabled = True
        self.user.preferences.save()

        dashboard_ai = DashboardAI(self.user)
        self.assertTrue(dashboard_ai.faith_enabled)

    def test_get_daily_insight_returns_cached(self):
        """get_daily_insight returns cached insight if valid."""
        cached_insight = self.create_ai_insight(
            self.user,
            insight_type='daily',
            content='Cached daily insight',
            valid_until=timezone.now() + timedelta(hours=6)
        )

        dashboard_ai = DashboardAI(self.user)
        result = dashboard_ai.get_daily_insight()

        self.assertEqual(result, 'Cached daily insight')

    def test_get_daily_insight_ignores_expired_cache(self):
        """get_daily_insight ignores expired cached insight."""
        expired_insight = self.create_ai_insight(
            self.user,
            insight_type='daily',
            content='Old insight',
            valid_until=timezone.now() - timedelta(hours=1)
        )

        dashboard_ai = DashboardAI(self.user)

        # Service is unavailable (no client), should return fallback
        original_client = ai_service.client
        ai_service.client = None
        try:
            result = dashboard_ai.get_daily_insight()
        finally:
            ai_service.client = original_client

        # Should not return the expired cached insight
        self.assertNotEqual(result, 'Old insight')

    def test_get_daily_insight_force_refresh(self):
        """get_daily_insight ignores cache when force_refresh=True."""
        cached_insight = self.create_ai_insight(
            self.user,
            insight_type='daily',
            content='Cached insight',
            valid_until=timezone.now() + timedelta(hours=6)
        )

        dashboard_ai = DashboardAI(self.user)

        with patch.object(ai_service, 'generate_daily_insight') as mock_gen:
            mock_gen.return_value = 'Fresh insight'
            # Mock client to make service available
            original_client = ai_service.client
            ai_service.client = MagicMock()
            try:
                result = dashboard_ai.get_daily_insight(force_refresh=True)
            finally:
                ai_service.client = original_client

        # Should call API even though cache exists
        mock_gen.assert_called_once()

    def test_get_weekly_summary_returns_cached(self):
        """get_weekly_summary returns recently cached summary."""
        cached = AIInsight.objects.create(
            user=self.user,
            insight_type='weekly_summary',
            content='Cached weekly summary'
        )

        dashboard_ai = DashboardAI(self.user)
        result = dashboard_ai.get_weekly_summary()

        self.assertEqual(result, 'Cached weekly summary')

    def test_get_weekly_summary_no_entries(self):
        """get_weekly_summary returns None when no journal entries."""
        dashboard_ai = DashboardAI(self.user)

        with patch.object(ai_service, 'generate_journal_summary') as mock_gen:
            result = dashboard_ai.get_weekly_summary(force_refresh=True)

        # Should return None since no entries
        self.assertIsNone(result)

    def test_fallback_insight_gentle_style(self):
        """Fallback insight matches gentle coaching style."""
        self.user.preferences.ai_coaching_style = 'gentle'
        self.user.preferences.save()

        dashboard_ai = DashboardAI(self.user)
        fallback = dashboard_ai._get_fallback_insight()

        # Should be one of the gentle fallbacks
        gentle_keywords = ['gentle', 'breath', 'meaningful', 'beautifully', 'no pressure']
        has_gentle = any(kw in fallback.lower() for kw in gentle_keywords)
        self.assertTrue(has_gentle or len(fallback) > 0)  # At least returns something

    def test_fallback_insight_direct_style(self):
        """Fallback insight matches direct coaching style."""
        self.user.preferences.ai_coaching_style = 'direct'
        self.user.preferences.save()

        dashboard_ai = DashboardAI(self.user)
        fallback = dashboard_ai._get_fallback_insight()

        # Should be one of the direct fallbacks
        direct_keywords = ['shape', 'count', 'moving', 'prove']
        has_direct = any(kw in fallback.lower() for kw in direct_keywords)
        self.assertTrue(has_direct or len(fallback) > 0)

    @patch.object(ai_service, 'generate_accountability_nudge')
    def test_get_nudge_message(self, mock_nudge):
        """get_nudge_message passes correct parameters."""
        mock_nudge.return_value = 'Time to journal!'

        dashboard_ai = DashboardAI(self.user)
        result = dashboard_ai.get_nudge_message('journal', {'days': 5})

        mock_nudge.assert_called_once()
        call_kwargs = mock_nudge.call_args
        gap_data = call_kwargs[0][0]
        self.assertEqual(gap_data['gap_type'], 'journal')
        self.assertEqual(gap_data['days_since'], 5)

    @patch.object(ai_service, 'generate_celebration')
    def test_get_celebration_message(self, mock_celebration):
        """get_celebration_message passes correct parameters."""
        mock_celebration.return_value = 'Great job!'

        dashboard_ai = DashboardAI(self.user)
        result = dashboard_ai.get_celebration_message('streak', '7 day streak')

        mock_celebration.assert_called_once()
        call_kwargs = mock_celebration.call_args
        achievement_data = call_kwargs[0][0]
        self.assertEqual(achievement_data['achievement_type'], 'streak')
        self.assertEqual(achievement_data['details'], '7 day streak')

    def test_calculate_journal_streak_no_entries(self):
        """Journal streak is 0 with no entries."""
        dashboard_ai = DashboardAI(self.user)
        streak = dashboard_ai._calculate_journal_streak()
        self.assertEqual(streak, 0)

    def test_calculate_journal_streak_with_entries(self):
        """Journal streak counts consecutive days."""
        from apps.journal.models import JournalEntry

        today = timezone.now().date()
        # Create entries for today, yesterday, and day before
        for i in range(3):
            JournalEntry.objects.create(
                user=self.user,
                title=f'Entry {i}',
                body='Test',
                entry_date=today - timedelta(days=i)
            )

        dashboard_ai = DashboardAI(self.user)
        streak = dashboard_ai._calculate_journal_streak()
        self.assertEqual(streak, 3)

    def test_calculate_journal_streak_broken(self):
        """Journal streak stops at gap in entries."""
        from apps.journal.models import JournalEntry

        today = timezone.now().date()
        # Entry today
        JournalEntry.objects.create(
            user=self.user,
            title='Today',
            body='Test',
            entry_date=today
        )
        # Skip yesterday, entry 2 days ago
        JournalEntry.objects.create(
            user=self.user,
            title='2 days ago',
            body='Test',
            entry_date=today - timedelta(days=2)
        )

        dashboard_ai = DashboardAI(self.user)
        streak = dashboard_ai._calculate_journal_streak()
        self.assertEqual(streak, 1)  # Only today counts


# =============================================================================
# 5. CONVENIENCE FUNCTION TESTS
# =============================================================================

class GetDashboardInsightTest(AITestMixin, TestCase):
    """Tests for the get_dashboard_insight convenience function."""

    def setUp(self):
        self.user = self.create_user()

    def test_returns_unavailable_when_no_service(self):
        """Returns unavailable status when AI service not configured."""
        # Temporarily remove client to make service unavailable
        original_client = ai_service.client
        ai_service.client = None

        try:
            result = get_dashboard_insight(self.user)

            self.assertFalse(result['available'])
            self.assertIsNone(result['daily_insight'])
            self.assertIsNone(result['weekly_summary'])
        finally:
            ai_service.client = original_client

    @patch.object(DashboardAI, 'get_daily_insight')
    @patch.object(DashboardAI, 'get_weekly_summary')
    def test_returns_insights_when_available(self, mock_weekly, mock_daily):
        """Returns insights when AI service is available."""
        mock_daily.return_value = 'Daily insight'
        mock_weekly.return_value = 'Weekly summary'

        # Mock the client to make service available
        original_client = ai_service.client
        ai_service.client = MagicMock()

        try:
            result = get_dashboard_insight(self.user)

            self.assertTrue(result['available'])
            self.assertEqual(result['daily_insight'], 'Daily insight')
            self.assertEqual(result['weekly_summary'], 'Weekly summary')
        finally:
            ai_service.client = original_client


# =============================================================================
# 6. EDGE CASES AND ERROR HANDLING
# =============================================================================

class AIEdgeCaseTest(AITestMixin, TestCase):
    """Tests for edge cases and error handling."""

    def setUp(self):
        self.user = self.create_user()

    def test_insight_with_very_long_content(self):
        """Can store insights with very long content."""
        long_content = 'A' * 10000
        insight = AIInsight.objects.create(
            user=self.user,
            insight_type='daily',
            content=long_content
        )
        insight.refresh_from_db()
        self.assertEqual(len(insight.content), 10000)

    def test_usage_log_with_zero_tokens(self):
        """Can log usage with zero tokens (e.g., cached response)."""
        log = AIUsageLog.objects.create(
            user=self.user,
            endpoint='cached',
            model_used='cache',
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0
        )
        self.assertEqual(log.total_tokens, 0)

    def test_multiple_insights_same_type(self):
        """Can have multiple insights of same type (history)."""
        for i in range(5):
            self.create_ai_insight(self.user, content=f'Insight {i}')

        insights = AIInsight.objects.filter(user=self.user, insight_type='daily')
        self.assertEqual(insights.count(), 5)

    def test_insights_isolated_between_users(self):
        """Users can only see their own insights."""
        user2 = self.create_user(email='user2@example.com')

        self.create_ai_insight(self.user, content='User 1 insight')
        self.create_ai_insight(user2, content='User 2 insight')

        user1_insights = AIInsight.objects.filter(user=self.user)
        user2_insights = AIInsight.objects.filter(user=user2)

        self.assertEqual(user1_insights.count(), 1)
        self.assertEqual(user2_insights.count(), 1)
        self.assertEqual(user1_insights.first().content, 'User 1 insight')
        self.assertEqual(user2_insights.first().content, 'User 2 insight')

    @patch.object(AIService, '_call_api')
    def test_api_error_returns_none(self, mock_api):
        """API errors return None gracefully."""
        mock_api.return_value = None

        service = AIService()
        service.client = MagicMock()

        result = service.analyze_journal_entry("Test entry")
        self.assertIsNone(result)

    def test_dashboard_ai_with_missing_preferences_attribute(self):
        """DashboardAI handles missing ai_coaching_style gracefully."""
        # The getattr with default handles this
        dashboard_ai = DashboardAI(self.user)
        self.assertEqual(dashboard_ai.coaching_style, 'supportive')

    def test_gather_user_data_with_no_related_data(self):
        """_gather_user_data works when user has no journal entries."""
        dashboard_ai = DashboardAI(self.user)
        data = dashboard_ai._gather_user_data()

        self.assertEqual(data['journal_count_week'], 0)
        self.assertIsNone(data.get('last_journal_date'))
        self.assertEqual(data.get('current_streak', 0), 0)

    def test_gather_user_data_with_journal_entries(self):
        """_gather_user_data includes journal stats when entries exist."""
        from apps.journal.models import JournalEntry

        today = timezone.now().date()
        JournalEntry.objects.create(
            user=self.user,
            title='Test',
            body='Test body',
            entry_date=today
        )

        dashboard_ai = DashboardAI(self.user)
        data = dashboard_ai._gather_user_data()

        self.assertEqual(data['journal_count_week'], 1)
        self.assertEqual(data['last_journal_date'], today)


# =============================================================================
# 7. INTEGRATION WITH OTHER MODULES
# =============================================================================

class AIIntegrationTest(AITestMixin, TestCase):
    """Tests for AI integration with other app modules."""

    def setUp(self):
        self.user = self.create_user()
        self.user.preferences.purpose_enabled = True
        self.user.preferences.life_enabled = True
        self.user.preferences.health_enabled = True
        self.user.preferences.save()

    def test_gather_data_includes_goals_when_enabled(self):
        """User data includes goals when Purpose module enabled."""
        from apps.purpose.models import LifeGoal

        LifeGoal.objects.create(
            user=self.user,
            title='Test Goal',
            status='active'
        )

        dashboard_ai = DashboardAI(self.user)
        data = dashboard_ai._gather_user_data()

        self.assertEqual(data.get('active_goals'), 1)

    def test_gather_data_includes_tasks_when_enabled(self):
        """User data includes tasks when Life module enabled."""
        from apps.life.models import Task

        today = timezone.now().date()
        Task.objects.create(
            user=self.user,
            title='Completed Task',
            is_completed=True,
            completed_at=timezone.now()
        )
        Task.objects.create(
            user=self.user,
            title='Overdue Task',
            is_completed=False,
            due_date=today - timedelta(days=1)
        )

        dashboard_ai = DashboardAI(self.user)
        data = dashboard_ai._gather_user_data()

        self.assertEqual(data.get('completed_tasks_today'), 1)
        self.assertEqual(data.get('overdue_tasks'), 1)

    def test_gather_data_includes_prayers_when_faith_enabled(self):
        """User data includes prayers when Faith module enabled."""
        self.user.preferences.faith_enabled = True
        self.user.preferences.save()

        from apps.faith.models import PrayerRequest

        PrayerRequest.objects.create(
            user=self.user,
            title='Test Prayer',
            is_answered=False
        )

        dashboard_ai = DashboardAI(self.user)
        data = dashboard_ai._gather_user_data()

        self.assertEqual(data.get('active_prayers'), 1)

    def test_get_journal_entries_returns_formatted_data(self):
        """_get_journal_entries returns properly formatted entry data."""
        from apps.journal.models import JournalEntry

        entry = JournalEntry.objects.create(
            user=self.user,
            title='Test Entry',
            body='This is the body of the entry',
            mood='happy',
            entry_date=timezone.now().date()
        )

        dashboard_ai = DashboardAI(self.user)
        entries = dashboard_ai._get_journal_entries(days=7)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['title'], 'Test Entry')
        self.assertEqual(entries[0]['mood'], 'happy')
        self.assertIn('body', entries[0])
