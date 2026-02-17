"""
Goal Engine Tests — Measurement-driven goal system.

Tests cover:
- Model fields and defaults (backward compatibility)
- Measurement type properties
- HabitEntry extended fields and auto-completion
- Streak service (daily/weekly/monthly)
- Analytics service
- Recommendation service
- Goal logging views (duration, count, target)
- Analytics and insights views

Location: apps/purpose/tests/test_goal_engine.py
"""

import json
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.purpose.models import HabitGoal, HabitEntry, GoalInsight
from apps.purpose.services import streak_service, analytics_service, recommendation_service
from apps.users.models import TermsAcceptance

User = get_user_model()


def create_test_user(email='test@example.com', password='testpass123'):
    """Create a test user with completed onboarding."""
    user = User.objects.create_user(email=email, password=password)
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def create_habit_goal(user, **kwargs):
    """Create a habit goal with sensible defaults."""
    defaults = {
        'name': 'Test Goal',
        'purpose': 'Test purpose',
        'start_date': date.today() - timedelta(days=30),
        'end_date': date.today() + timedelta(days=30),
        'habit_required': True,
        'status': 'active',
        'measurement_type': 'binary',
    }
    defaults.update(kwargs)
    return HabitGoal.objects.create(user=user, **defaults)


# =============================================================================
# Model Tests
# =============================================================================

class TestMeasurementTypes(TestCase):
    """Test HabitGoal measurement type fields and properties."""

    def setUp(self):
        self.user = create_test_user()

    def test_default_measurement_type_is_binary(self):
        """New goals default to binary measurement type."""
        goal = create_habit_goal(self.user)
        self.assertEqual(goal.measurement_type, 'binary')

    def test_create_duration_goal(self):
        """Duration goal can be created with target."""
        goal = create_habit_goal(
            self.user,
            measurement_type='duration',
            target_value=Decimal('30'),
            target_unit='minutes',
        )
        self.assertTrue(goal.is_duration)
        self.assertFalse(goal.is_binary)
        self.assertEqual(goal.target_unit_display, 'minutes')

    def test_create_count_goal(self):
        """Count goal can be created."""
        goal = create_habit_goal(
            self.user,
            measurement_type='count',
            target_value=Decimal('50'),
            target_unit='pushups',
        )
        self.assertTrue(goal.is_count)
        self.assertFalse(goal.is_duration)

    def test_create_target_goal(self):
        """Target goal can be created."""
        goal = create_habit_goal(
            self.user,
            measurement_type='target',
            target_value=Decimal('10000'),
            target_unit='words',
        )
        self.assertTrue(goal.is_target)

    def test_measurement_icon(self):
        """Each measurement type has an icon."""
        for mtype, icon in [('binary', '\u2713'), ('duration', '\u23f1'), ('count', '#'), ('target', '\U0001f3af')]:
            goal = create_habit_goal(
                self.user,
                name=f'{mtype} Goal',
                measurement_type=mtype,
            )
            self.assertEqual(goal.measurement_icon, icon)

    def test_backward_compatibility_existing_goals(self):
        """Existing binary goals work unchanged with new fields."""
        goal = create_habit_goal(self.user)
        self.assertIsNone(goal.target_value)
        self.assertIsNone(goal.sessions_per_week)
        self.assertEqual(goal.category, '')
        self.assertEqual(goal.frequency_type, 'daily')

    def test_frequency_type_choices(self):
        """All frequency types are valid."""
        for freq in ['daily', 'weekly', 'monthly']:
            goal = create_habit_goal(
                self.user,
                name=f'{freq} Goal',
                frequency_type=freq,
            )
            self.assertEqual(goal.frequency_type, freq)


class TestHabitEntryExtended(TestCase):
    """Test HabitEntry with measurement fields."""

    def setUp(self):
        self.user = create_test_user()

    def test_duration_entry_auto_completed(self):
        """Duration entry sets completed=True when meeting target."""
        goal = create_habit_goal(
            self.user,
            measurement_type='duration',
            target_value=Decimal('30'),
        )
        entry = HabitEntry(
            goal=goal,
            date=date.today(),
            duration_minutes=Decimal('35'),
        )
        entry.save()
        self.assertTrue(entry.completed)

    def test_duration_entry_below_target_not_completed(self):
        """Duration entry below target is not auto-completed."""
        goal = create_habit_goal(
            self.user,
            measurement_type='duration',
            target_value=Decimal('30'),
        )
        entry = HabitEntry(
            goal=goal,
            date=date.today(),
            duration_minutes=Decimal('15'),
        )
        entry.save()
        self.assertFalse(entry.completed)

    def test_count_entry_auto_completed(self):
        """Count entry sets completed when meeting target."""
        goal = create_habit_goal(
            self.user,
            measurement_type='count',
            target_value=Decimal('50'),
        )
        entry = HabitEntry(
            goal=goal,
            date=date.today(),
            count_value=Decimal('60'),
        )
        entry.save()
        self.assertTrue(entry.completed)

    def test_multiple_sessions_same_day(self):
        """Multiple entries can be logged on same day with different session numbers."""
        goal = create_habit_goal(
            self.user,
            measurement_type='duration',
            target_value=Decimal('30'),
        )
        entry1 = HabitEntry.objects.create(
            goal=goal,
            date=date.today(),
            duration_minutes=Decimal('30'),
            session_number=1,
        )
        entry2 = HabitEntry.objects.create(
            goal=goal,
            date=date.today(),
            duration_minutes=Decimal('20'),
            session_number=2,
        )
        self.assertEqual(entry1.session_number, 1)
        self.assertEqual(entry2.session_number, 2)

    def test_get_next_session_number(self):
        """Next session number increments correctly."""
        goal = create_habit_goal(self.user, measurement_type='duration')
        today = date.today()
        # Create an unsaved entry to call the instance method
        entry = HabitEntry(goal=goal, date=today)
        self.assertEqual(entry.get_next_session_number(), 1)
        HabitEntry.objects.create(
            goal=goal, date=today, session_number=1,
            duration_minutes=Decimal('10'),
        )
        entry2 = HabitEntry(goal=goal, date=today)
        self.assertEqual(entry2.get_next_session_number(), 2)

    def test_binary_entry_unchanged(self):
        """Binary entries still work as before."""
        goal = create_habit_goal(self.user, measurement_type='binary')
        entry = HabitEntry.objects.create(
            goal=goal,
            date=date.today(),
            completed=True,
        )
        self.assertTrue(entry.completed)
        self.assertIsNone(entry.duration_minutes)
        self.assertIsNone(entry.count_value)


class TestGoalInsightModel(TestCase):
    """Test GoalInsight model."""

    def setUp(self):
        self.user = create_test_user()
        self.goal = create_habit_goal(self.user)

    def test_create_insight(self):
        """Insight can be created."""
        insight = GoalInsight.objects.create(
            goal=self.goal,
            insight_type='encouragement',
            title='Great Job!',
            message='Keep it up.',
            suggestion_data={},
        )
        self.assertFalse(insight.is_dismissed)
        self.assertFalse(insight.is_applied)

    def test_insight_with_suggestion(self):
        """Insight can hold suggestion data."""
        insight = GoalInsight.objects.create(
            goal=self.goal,
            insight_type='optimization',
            title='Increase Target',
            message='You can do more.',
            suggestion_data={'new_target': 40},
        )
        self.assertEqual(insight.suggestion_data['new_target'], 40)


# =============================================================================
# Streak Service Tests
# =============================================================================

class TestStreakService(TestCase):
    """Test streak calculation service."""

    def setUp(self):
        self.user = create_test_user()

    def test_empty_streak(self):
        """No entries means zero streak."""
        goal = create_habit_goal(self.user)
        data = streak_service.get_streak_data(goal)
        self.assertEqual(data.current, 0)
        self.assertEqual(data.longest, 0)

    def test_daily_streak_consecutive(self):
        """Consecutive daily entries produce correct streak."""
        goal = create_habit_goal(self.user, measurement_type='binary')
        today = date.today()
        for i in range(5):
            HabitEntry.objects.create(
                goal=goal,
                date=today - timedelta(days=i),
                completed=True,
            )
        streak = streak_service.get_current_streak(goal)
        self.assertEqual(streak, 5)

    def test_daily_streak_broken(self):
        """Gap in entries resets streak."""
        goal = create_habit_goal(self.user, measurement_type='binary')
        today = date.today()
        # Log today and yesterday
        HabitEntry.objects.create(goal=goal, date=today, completed=True)
        HabitEntry.objects.create(goal=goal, date=today - timedelta(days=1), completed=True)
        # Skip a day, then log 3 days ago
        HabitEntry.objects.create(goal=goal, date=today - timedelta(days=3), completed=True)

        streak = streak_service.get_current_streak(goal)
        self.assertEqual(streak, 2)

    def test_longest_streak(self):
        """Longest streak finds historical best."""
        goal = create_habit_goal(
            self.user,
            start_date=date.today() - timedelta(days=60),
        )
        today = date.today()
        # Current streak: 2 days
        HabitEntry.objects.create(goal=goal, date=today, completed=True)
        HabitEntry.objects.create(goal=goal, date=today - timedelta(days=1), completed=True)
        # Historical streak: 4 days (30 days ago)
        for i in range(4):
            HabitEntry.objects.create(
                goal=goal,
                date=today - timedelta(days=30 + i),
                completed=True,
            )
        longest = streak_service.get_longest_streak(goal)
        self.assertEqual(longest, 4)

    def test_weekly_streak(self):
        """Weekly streak counts weeks meeting sessions_per_week."""
        today = date.today()
        # Use a previous full week so all 3 entries fit in a single ISO week
        # without risking future dates or spanning a week boundary.
        monday_last_week = today - timedelta(days=today.weekday() + 7)
        goal = create_habit_goal(
            self.user,
            measurement_type='duration',
            frequency_type='weekly',
            sessions_per_week=3,
            start_date=monday_last_week - timedelta(days=7),
        )
        # Last week: 3 sessions (Mon, Tue, Wed)
        for i in range(3):
            HabitEntry.objects.create(
                goal=goal,
                date=monday_last_week + timedelta(days=i),
                duration_minutes=Decimal('30'),
                session_number=1,
            )
        streak = streak_service.get_current_streak(goal)
        self.assertGreaterEqual(streak, 1)

    def test_at_risk_detection(self):
        """At-risk flag set when streak could break today."""
        goal = create_habit_goal(self.user, measurement_type='binary')
        today = date.today()
        # Yesterday logged but not today
        HabitEntry.objects.create(
            goal=goal,
            date=today - timedelta(days=1),
            completed=True,
        )
        data = streak_service.get_streak_data(goal)
        # Streak starts from yesterday, and today is not logged -> at_risk
        self.assertTrue(data.at_risk)


# =============================================================================
# Analytics Service Tests
# =============================================================================

class TestAnalyticsService(TestCase):
    """Test analytics calculations."""

    def setUp(self):
        self.user = create_test_user()

    def test_empty_analytics(self):
        """Analytics for goal with no entries."""
        goal = create_habit_goal(self.user)
        analytics = analytics_service.get_analytics(goal, days=30)
        self.assertEqual(analytics.total_sessions, 0)
        self.assertEqual(analytics.completion_rate, 0)

    def test_completion_rate(self):
        """Completion rate calculated correctly."""
        goal = create_habit_goal(
            self.user,
            start_date=date.today() - timedelta(days=9),
        )
        today = date.today()
        # 7 out of 10 days completed
        for i in range(7):
            HabitEntry.objects.create(
                goal=goal,
                date=today - timedelta(days=i),
                completed=True,
            )
        analytics = analytics_service.get_analytics(goal, days=10)
        self.assertEqual(analytics.total_sessions, 7)
        self.assertGreater(analytics.completion_rate, 0)

    def test_day_of_week_breakdown(self):
        """Day-of-week breakdown returns data."""
        goal = create_habit_goal(
            self.user,
            start_date=date.today() - timedelta(days=30),
        )
        today = date.today()
        for i in range(14):
            HabitEntry.objects.create(
                goal=goal,
                date=today - timedelta(days=i),
                completed=True,
            )
        analytics = analytics_service.get_analytics(goal, days=30)
        self.assertIsNotNone(analytics.day_of_week_breakdown)
        self.assertGreater(len(analytics.day_of_week_breakdown), 0)

    def test_trend_detection(self):
        """Trend direction is calculated."""
        goal = create_habit_goal(
            self.user,
            start_date=date.today() - timedelta(days=30),
        )
        today = date.today()
        for i in range(14):
            HabitEntry.objects.create(
                goal=goal,
                date=today - timedelta(days=i),
                completed=True,
            )
        analytics = analytics_service.get_analytics(goal, days=30)
        self.assertIn(analytics.trend_direction, ['improving', 'declining', 'stable'])

    def test_analytics_to_dict(self):
        """Analytics can be serialized to dict."""
        goal = create_habit_goal(self.user)
        analytics = analytics_service.get_analytics(goal, days=7)
        result = analytics_service.analytics_to_dict(analytics)
        self.assertIsInstance(result, dict)
        self.assertIn('completion_rate', result)
        self.assertIn('total_sessions', result)

    def test_duration_goal_avg_duration(self):
        """Average duration calculated for duration goals."""
        goal = create_habit_goal(
            self.user,
            measurement_type='duration',
            target_value=Decimal('30'),
            start_date=date.today() - timedelta(days=10),
        )
        today = date.today()
        for i in range(5):
            HabitEntry.objects.create(
                goal=goal,
                date=today - timedelta(days=i),
                duration_minutes=Decimal(str(20 + i * 5)),
                session_number=1,
            )
        analytics = analytics_service.get_analytics(goal, days=10)
        self.assertIsNotNone(analytics.avg_duration)
        self.assertGreater(analytics.avg_duration, 0)


# =============================================================================
# Recommendation Service Tests
# =============================================================================

class TestRecommendationService(TestCase):
    """Test insight generation and management."""

    def setUp(self):
        self.user = create_test_user()

    def test_no_insights_for_new_goal(self):
        """No insights generated for goals with <3 sessions."""
        goal = create_habit_goal(self.user)
        HabitEntry.objects.create(
            goal=goal, date=date.today(), completed=True,
        )
        insights = recommendation_service.generate_insights(goal)
        self.assertEqual(len(insights), 0)

    def test_dismiss_insight(self):
        """Insight can be dismissed."""
        goal = create_habit_goal(self.user)
        insight = GoalInsight.objects.create(
            goal=goal,
            insight_type='encouragement',
            title='Test',
            message='Test message',
            suggestion_data={},
        )
        result = recommendation_service.dismiss_insight(insight.pk)
        self.assertTrue(result)
        insight.refresh_from_db()
        self.assertTrue(insight.is_dismissed)

    def test_dismiss_nonexistent(self):
        """Dismissing nonexistent insight returns False."""
        result = recommendation_service.dismiss_insight(99999)
        self.assertFalse(result)

    def test_apply_target_suggestion(self):
        """Applying suggestion updates goal target."""
        goal = create_habit_goal(
            self.user,
            measurement_type='duration',
            target_value=Decimal('30'),
        )
        insight = GoalInsight.objects.create(
            goal=goal,
            insight_type='optimization',
            title='Increase',
            message='Increase target',
            suggestion_data={'new_target': 35},
        )
        result = recommendation_service.apply_insight(insight.pk)
        self.assertTrue(result)
        goal.refresh_from_db()
        self.assertEqual(goal.target_value, Decimal('35'))
        insight.refresh_from_db()
        self.assertTrue(insight.is_applied)
        self.assertTrue(insight.is_dismissed)

    def test_apply_sessions_suggestion(self):
        """Applying sessions_per_week suggestion updates goal."""
        goal = create_habit_goal(
            self.user,
            measurement_type='count',
            sessions_per_week=3,
        )
        insight = GoalInsight.objects.create(
            goal=goal,
            insight_type='optimization',
            title='More Sessions',
            message='Add more sessions',
            suggestion_data={'new_sessions_per_week': 5},
        )
        result = recommendation_service.apply_insight(insight.pk)
        self.assertTrue(result)
        goal.refresh_from_db()
        self.assertEqual(goal.sessions_per_week, 5)

    def test_get_active_insights(self):
        """Active insights excludes dismissed ones."""
        goal = create_habit_goal(self.user)
        GoalInsight.objects.create(
            goal=goal, insight_type='encouragement',
            title='Active', message='Active', suggestion_data={},
        )
        GoalInsight.objects.create(
            goal=goal, insight_type='warning',
            title='Dismissed', message='Dismissed', suggestion_data={},
            is_dismissed=True,
        )
        active = recommendation_service.get_active_insights(goal)
        self.assertEqual(active.count(), 1)
        self.assertEqual(active.first().title, 'Active')


# =============================================================================
# View Tests
# =============================================================================

class TestGoalLogViews(TestCase):
    """Test the goal logging AJAX endpoints."""

    def setUp(self):
        self.user = create_test_user()
        self.client = Client()
        self.client.login(email='test@example.com', password='testpass123')

    def test_log_duration_success(self):
        """POST to log-duration creates entry."""
        goal = create_habit_goal(
            self.user,
            measurement_type='duration',
            target_value=Decimal('30'),
        )
        url = reverse('purpose:goal_log_duration', kwargs={'pk': goal.pk})
        response = self.client.post(
            url,
            json.dumps({'duration_minutes': 25}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(HabitEntry.objects.filter(goal=goal).exists())

    def test_log_duration_wrong_type(self):
        """log-duration rejects binary goals."""
        goal = create_habit_goal(self.user, measurement_type='binary')
        url = reverse('purpose:goal_log_duration', kwargs={'pk': goal.pk})
        response = self.client.post(
            url,
            json.dumps({'duration_minutes': 25}),
            content_type='application/json',
        )
        data = response.json()
        self.assertFalse(data['success'])

    def test_log_count_success(self):
        """POST to log-count creates/updates entry."""
        goal = create_habit_goal(
            self.user,
            measurement_type='count',
            target_value=Decimal('50'),
        )
        url = reverse('purpose:goal_log_count', kwargs={'pk': goal.pk})
        response = self.client.post(
            url,
            json.dumps({'count_value': 30}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

    def test_log_target_success(self):
        """POST to log-target creates/updates entry."""
        goal = create_habit_goal(
            self.user,
            measurement_type='target',
            target_value=Decimal('10000'),
            target_unit='words',
        )
        url = reverse('purpose:goal_log_target', kwargs={'pk': goal.pk})
        response = self.client.post(
            url,
            json.dumps({'target_value': 500}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

    def test_log_requires_auth(self):
        """Logging endpoints require authentication."""
        self.client.logout()
        goal = create_habit_goal(self.user, measurement_type='duration')
        url = reverse('purpose:goal_log_duration', kwargs={'pk': goal.pk})
        response = self.client.post(
            url,
            json.dumps({'duration_minutes': 25}),
            content_type='application/json',
        )
        self.assertNotEqual(response.status_code, 200)

    def test_log_other_users_goal(self):
        """Cannot log to another user's goal."""
        other_user = create_test_user(email='other@example.com')
        goal = create_habit_goal(other_user, measurement_type='duration')
        url = reverse('purpose:goal_log_duration', kwargs={'pk': goal.pk})
        response = self.client.post(
            url,
            json.dumps({'duration_minutes': 25}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)


class TestGoalAnalyticsView(TestCase):
    """Test analytics JSON endpoint."""

    def setUp(self):
        self.user = create_test_user()
        self.client = Client()
        self.client.login(email='test@example.com', password='testpass123')

    def test_analytics_returns_json(self):
        """GET analytics returns JSON with expected keys."""
        goal = create_habit_goal(self.user)
        url = reverse('purpose:goal_analytics', kwargs={'pk': goal.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('analytics', data)
        self.assertIn('completion_rate', data['analytics'])

    def test_analytics_requires_auth(self):
        """Analytics requires authentication."""
        self.client.logout()
        goal = create_habit_goal(self.user)
        url = reverse('purpose:goal_analytics', kwargs={'pk': goal.pk})
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, 200)


class TestGoalInsightViews(TestCase):
    """Test insight dismiss/apply endpoints."""

    def setUp(self):
        self.user = create_test_user()
        self.client = Client()
        self.client.login(email='test@example.com', password='testpass123')

    def test_get_insights(self):
        """GET insights returns list."""
        goal = create_habit_goal(self.user)
        GoalInsight.objects.create(
            goal=goal,
            insight_type='encouragement',
            title='Test',
            message='Message',
            suggestion_data={},
        )
        url = reverse('purpose:goal_insights', kwargs={'pk': goal.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('insights', data)
        self.assertEqual(len(data['insights']), 1)

    def test_dismiss_insight_view(self):
        """POST to dismiss endpoint works."""
        goal = create_habit_goal(self.user)
        insight = GoalInsight.objects.create(
            goal=goal,
            insight_type='warning',
            title='Test',
            message='Message',
            suggestion_data={},
        )
        url = reverse('purpose:goal_insight_dismiss', kwargs={'pk': insight.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        insight.refresh_from_db()
        self.assertTrue(insight.is_dismissed)

    def test_apply_insight_view(self):
        """POST to apply endpoint works."""
        goal = create_habit_goal(
            self.user,
            measurement_type='duration',
            target_value=Decimal('30'),
        )
        insight = GoalInsight.objects.create(
            goal=goal,
            insight_type='optimization',
            title='Increase',
            message='Msg',
            suggestion_data={'new_target': 40},
        )
        url = reverse('purpose:goal_insight_apply', kwargs={'pk': insight.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        goal.refresh_from_db()
        self.assertEqual(goal.target_value, Decimal('40'))


class TestHabitGoalFormViews(TestCase):
    """Test create/update views with measurement fields."""

    def setUp(self):
        self.user = create_test_user()
        self.client = Client()
        self.client.login(email='test@example.com', password='testpass123')

    def test_create_view_loads(self):
        """Create view loads without error."""
        url = reverse('purpose:habit_goal_create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_update_view_loads(self):
        """Update view loads without error."""
        goal = create_habit_goal(self.user)
        url = reverse('purpose:habit_goal_update', kwargs={'pk': goal.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_detail_view_binary(self):
        """Detail view loads for binary goal."""
        goal = create_habit_goal(self.user, measurement_type='binary')
        url = reverse('purpose:habit_goal_detail', kwargs={'pk': goal.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_detail_view_duration(self):
        """Detail view loads for duration goal."""
        goal = create_habit_goal(
            self.user,
            measurement_type='duration',
            target_value=Decimal('30'),
            target_unit='minutes',
        )
        url = reverse('purpose:habit_goal_detail', kwargs={'pk': goal.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_detail_view_count(self):
        """Detail view loads for count goal."""
        goal = create_habit_goal(
            self.user,
            measurement_type='count',
            target_value=Decimal('50'),
            target_unit='reps',
        )
        url = reverse('purpose:habit_goal_detail', kwargs={'pk': goal.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_detail_view_target(self):
        """Detail view loads for target goal."""
        goal = create_habit_goal(
            self.user,
            measurement_type='target',
            target_value=Decimal('1000'),
            target_unit='pages',
        )
        url = reverse('purpose:habit_goal_detail', kwargs={'pk': goal.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_list_view_loads(self):
        """List view loads with measurement badges."""
        create_habit_goal(self.user, measurement_type='binary', name='Binary')
        create_habit_goal(self.user, measurement_type='duration', name='Duration')
        url = reverse('purpose:habit_goal_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class TestHabitGoalHelperProperties(TestCase):
    """Test computed properties on HabitGoal."""

    def setUp(self):
        self.user = create_test_user()

    def test_avg_duration(self):
        """avg_duration returns average for duration goals."""
        goal = create_habit_goal(
            self.user,
            measurement_type='duration',
            start_date=date.today() - timedelta(days=10),
        )
        HabitEntry.objects.create(
            goal=goal, date=date.today(), duration_minutes=Decimal('30'),
        )
        HabitEntry.objects.create(
            goal=goal, date=date.today() - timedelta(days=1),
            duration_minutes=Decimal('20'),
        )
        self.assertAlmostEqual(float(goal.avg_duration), 25.0)

    def test_total_count(self):
        """total_count sums count entries."""
        goal = create_habit_goal(
            self.user,
            measurement_type='count',
            start_date=date.today() - timedelta(days=10),
        )
        HabitEntry.objects.create(
            goal=goal, date=date.today(), count_value=Decimal('10'),
        )
        HabitEntry.objects.create(
            goal=goal, date=date.today() - timedelta(days=1),
            count_value=Decimal('15'),
        )
        self.assertEqual(goal.total_count, Decimal('25'))

    def test_running_total(self):
        """running_total sums target entries."""
        goal = create_habit_goal(
            self.user,
            measurement_type='target',
            start_date=date.today() - timedelta(days=10),
        )
        HabitEntry.objects.create(
            goal=goal, date=date.today(), target_value=Decimal('100'),
        )
        HabitEntry.objects.create(
            goal=goal, date=date.today() - timedelta(days=1),
            target_value=Decimal('200'),
        )
        self.assertEqual(goal.running_total, Decimal('300'))

    def test_weekly_session_count(self):
        """get_weekly_session_count returns this week's sessions."""
        goal = create_habit_goal(
            self.user,
            measurement_type='duration',
            start_date=date.today() - timedelta(days=30),
        )
        today = date.today()
        # Get start of current ISO week (Monday)
        week_start = today - timedelta(days=today.weekday())
        HabitEntry.objects.create(
            goal=goal, date=week_start, duration_minutes=Decimal('30'),
        )
        HabitEntry.objects.create(
            goal=goal, date=week_start + timedelta(days=1),
            duration_minutes=Decimal('25'),
        )
        count = goal.get_weekly_session_count()
        self.assertGreaterEqual(count, 2)
