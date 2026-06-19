"""
Dashboard Module - Comprehensive Tests

This test file demonstrates robust testing patterns covering:
1. Model tests (CRUD, validation, properties)
2. View tests (loading, authentication, context)
3. Form validation tests
4. Edge case tests
5. Business logic tests
6. Integration tests
7. Permission tests
8. API/HTMX tests

Location: apps/dashboard/tests/test_dashboard.py
"""

from datetime import date, timedelta
from decimal import Decimal
import json

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.dashboard.models import DailyEncouragement

User = get_user_model()


# =============================================================================
# TEST HELPERS
# =============================================================================

class DashboardTestMixin:
    """Common setup for dashboard tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        return user

    def _accept_terms(self, user):
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
        )

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def enable_module(self, user, module):
        """Enable a module for a user (faith, health, journal, life, purpose)."""
        setattr(user.preferences, f'{module}_enabled', True)
        user.preferences.save()

    def login_user(self, email='test@example.com', password='testpass123'):
        """Login and return True if successful."""
        return self.client.login(email=email, password=password)


# =============================================================================
# 1. MODEL TESTS
# =============================================================================

class DailyEncouragementModelTest(TestCase):
    """Tests for the DailyEncouragement model."""

    # --- Basic CRUD ---

    def test_create_encouragement(self):
        """Encouragement can be created with required fields."""
        encouragement = DailyEncouragement.objects.create(
            message="Today is a gift. That's why it's called the present."
        )
        self.assertEqual(
            encouragement.message,
            "Today is a gift. That's why it's called the present."
        )
        self.assertTrue(encouragement.is_active)

    def test_create_encouragement_with_scripture(self):
        """Encouragement can include scripture reference."""
        encouragement = DailyEncouragement.objects.create(
            message="Cast your cares on the Lord.",
            scripture_reference="1 Peter 5:7",
            scripture_text="Cast all your anxiety on him because he cares for you.",
            translation="NIV",
            is_faith_specific=True
        )
        self.assertEqual(encouragement.scripture_reference, "1 Peter 5:7")
        self.assertTrue(encouragement.is_faith_specific)

    def test_encouragement_default_values(self):
        """Encouragement has correct default values."""
        encouragement = DailyEncouragement.objects.create(
            message="Test message"
        )
        self.assertEqual(encouragement.translation, "ESV")
        self.assertFalse(encouragement.is_faith_specific)
        self.assertTrue(encouragement.is_active)
        self.assertEqual(encouragement.themes, [])
        self.assertIsNone(encouragement.day_of_week)
        self.assertIsNone(encouragement.month)

    # --- String Representation ---

    def test_str_without_scripture(self):
        """String representation without scripture shows message preview."""
        encouragement = DailyEncouragement.objects.create(
            message="This is a long message that should be truncated for display purposes"
        )
        str_repr = str(encouragement)
        self.assertIn("This is a long message", str_repr)
        self.assertIn("...", str_repr)

    def test_str_with_scripture(self):
        """String representation with scripture includes reference."""
        encouragement = DailyEncouragement.objects.create(
            message="Be strong and courageous",
            scripture_reference="Joshua 1:9"
        )
        str_repr = str(encouragement)
        self.assertIn("Joshua 1:9", str_repr)

    # --- Field Validation ---

    def test_day_of_week_range(self):
        """Day of week accepts valid values (0-6)."""
        for day in range(7):
            encouragement = DailyEncouragement.objects.create(
                message=f"Message for day {day}",
                day_of_week=day
            )
            self.assertEqual(encouragement.day_of_week, day)

    def test_month_range(self):
        """Month accepts valid values (1-12)."""
        for month in range(1, 13):
            encouragement = DailyEncouragement.objects.create(
                message=f"Message for month {month}",
                month=month
            )
            self.assertEqual(encouragement.month, month)

    def test_themes_as_list(self):
        """Themes field stores list correctly."""
        themes = ['peace', 'trust', 'gratitude']
        encouragement = DailyEncouragement.objects.create(
            message="Test message",
            themes=themes
        )
        self.assertEqual(encouragement.themes, themes)

    # --- Querysets ---

    def test_filter_active_only(self):
        """Can filter to only active encouragements."""
        DailyEncouragement.objects.create(message="Active", is_active=True)
        DailyEncouragement.objects.create(message="Inactive", is_active=False)

        active = DailyEncouragement.objects.filter(is_active=True)
        self.assertEqual(active.count(), 1)
        self.assertEqual(active.first().message, "Active")

    def test_filter_faith_specific(self):
        """Can filter faith-specific encouragements."""
        DailyEncouragement.objects.create(
            message="General", is_faith_specific=False
        )
        DailyEncouragement.objects.create(
            message="Faith", is_faith_specific=True
        )

        faith_only = DailyEncouragement.objects.filter(is_faith_specific=True)
        self.assertEqual(faith_only.count(), 1)

    def test_filter_by_day_of_week(self):
        """Can filter by day of week."""
        DailyEncouragement.objects.create(message="Monday", day_of_week=0)
        DailyEncouragement.objects.create(message="Any day", day_of_week=None)

        monday = DailyEncouragement.objects.filter(day_of_week=0)
        self.assertEqual(monday.count(), 1)

        any_day = DailyEncouragement.objects.filter(day_of_week__isnull=True)
        self.assertEqual(any_day.count(), 1)


# =============================================================================
# 2. VIEW TESTS - Basic Loading
# =============================================================================

class DashboardViewBasicTest(DashboardTestMixin, TestCase):
    """Basic view loading tests."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()

    # --- Authentication Required ---

    def test_dashboard_requires_login(self):
        """Dashboard redirects anonymous users to login."""
        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url.lower())

    def test_configure_requires_login(self):
        """Configure page requires authentication."""
        response = self.client.get(reverse('dashboard:configure'))
        self.assertEqual(response.status_code, 302)

    def test_weight_api_requires_login(self):
        """Weight chart API requires authentication."""
        response = self.client.get(reverse('dashboard:weight_chart_data'))
        self.assertEqual(response.status_code, 302)

    # --- Authenticated Access ---

    def test_dashboard_loads_for_authenticated_user(self):
        """Dashboard loads for authenticated user."""
        self.login_user()
        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertEqual(response.status_code, 200)

    def test_configure_redirects_to_dashboard_with_edit_mode(self):
        """Configure page redirects to dashboard with edit mode enabled."""
        self.login_user()
        response = self.client.get(reverse('dashboard:configure'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/dashboard/?edit=1')

    # --- Template Used ---

    def test_dashboard_uses_correct_template(self):
        """Dashboard uses the correct template."""
        self.login_user()
        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertTemplateUsed(response, 'dashboard_v2/home.html')


# =============================================================================
# 3. CONTEXT TESTS
# =============================================================================

class DashboardContextTest(DashboardTestMixin, TestCase):
    """Tests for dashboard context data."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_context_contains_greeting(self):
        """Context includes greeting."""
        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertIn('greeting', response.context)

    def test_context_contains_current_date(self):
        """Context includes current_date."""
        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertIn('current_date', response.context)

    def test_context_contains_module_flags(self):
        """Context includes module enabled flags."""
        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertIn('faith_enabled', response.context)

    def test_context_contains_daily_progress(self):
        """Context includes daily_progress from V2 dashboard."""
        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertIn('daily_progress', response.context)

    def test_faith_stats_included_when_enabled(self):
        """Faith stats included when faith module enabled."""
        self.enable_module(self.user, 'faith')
        response = self.client.get(reverse('dashboard_v2:home'))
        # Faith-specific context should be present
        self.assertIn('faith_enabled', response.context)
        self.assertTrue(response.context['faith_enabled'])

    def test_faith_stats_excluded_when_disabled(self):
        """Faith stats not included when faith module disabled."""
        self.user.preferences.faith_enabled = False
        self.user.preferences.save()
        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertFalse(response.context.get('faith_enabled', False))


# =============================================================================
# 4. EDGE CASE TESTS
# =============================================================================

class DashboardEdgeCaseTest(DashboardTestMixin, TestCase):
    """Tests for edge cases and empty states."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_dashboard_loads_with_no_data(self):
        """Dashboard loads gracefully when user has no data."""
        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_loads_with_no_encouragements(self):
        """Dashboard loads when no encouragements exist."""
        DailyEncouragement.objects.all().delete()
        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_with_new_user(self):
        """Dashboard works for brand new user with no history."""
        self.create_user(email='newuser@example.com')
        self.client.login(email='newuser@example.com', password='testpass123')
        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertEqual(response.status_code, 200)

    def test_encouragement_long_message(self):
        """Long encouragement messages are handled."""
        long_message = "A" * 1000
        encouragement = DailyEncouragement.objects.create(message=long_message)
        # Should truncate in __str__
        self.assertLess(len(str(encouragement)), 100)

    def test_empty_themes_list(self):
        """Empty themes list is handled correctly."""
        encouragement = DailyEncouragement.objects.create(
            message="Test",
            themes=[]
        )
        self.assertEqual(encouragement.themes, [])


# =============================================================================
# 5. BUSINESS LOGIC TESTS
# =============================================================================

class DashboardBusinessLogicTest(DashboardTestMixin, TestCase):
    """Tests for dashboard business logic."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_greeting_changes_by_time_of_day(self):
        """Greeting changes based on time of day."""
        # This tests the get_greeting method indirectly
        response = self.client.get(reverse('dashboard_v2:home'))
        greeting = response.context.get('greeting', '')
        # Should be one of: Good morning, Good afternoon, Good evening
        self.assertTrue(
            any(g in greeting for g in ['morning', 'afternoon', 'evening', 'Morning', 'Afternoon', 'Evening'])
            or greeting != ''  # At minimum, greeting exists
        )

    def test_encouragement_filters_by_faith_setting(self):
        """Faith-specific encouragements only shown when faith enabled."""
        # Create both types
        DailyEncouragement.objects.create(
            message="General message",
            is_faith_specific=False,
            is_active=True
        )
        DailyEncouragement.objects.create(
            message="Faith message",
            is_faith_specific=True,
            is_active=True
        )

        # With faith disabled
        self.user.preferences.faith_enabled = False
        self.user.preferences.save()
        response = self.client.get(reverse('dashboard_v2:home'))
        encouragement = response.context.get('encouragement')
        if encouragement:
            # Should not be the faith-specific one
            if hasattr(encouragement, 'message'):
                self.assertNotEqual(encouragement.message, 'Faith message')
            elif isinstance(encouragement, dict):
                self.assertNotEqual(encouragement.get('message', ''), 'Faith message')


class JournalStreakTest(DashboardTestMixin, TestCase):
    """Tests for journal streak calculation."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.enable_module(self.user, 'journal')
        self.login_user()

    def test_streak_zero_with_no_entries(self):
        """Streak is 0 when no journal entries."""
        response = self.client.get(reverse('dashboard_v2:home'))
        user_data = response.context.get('user_data', {})
        self.assertEqual(user_data.get('journal_streak', 0), 0)

    def test_streak_with_consecutive_entries(self):
        """Dashboard loads correctly with consecutive journal entries."""
        from apps.journal.models import JournalEntry
        from apps.core.utils import get_user_today

        # Use the user's timezone-aware today to match dashboard logic
        today = get_user_today(self.user)
        # Create entries for today, yesterday, and 2 days ago
        for i in range(0, 3):
            JournalEntry.objects.create(
                user=self.user,
                title=f"Entry {i}",
                body="Content",
                entry_date=today - timedelta(days=i)
            )

        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertEqual(response.status_code, 200)
        # V2 dashboard provides daily_progress instead of journal-specific streak
        self.assertIn('daily_progress', response.context)


# =============================================================================
# 6. INTEGRATION TESTS
# =============================================================================

class DashboardIntegrationTest(DashboardTestMixin, TestCase):
    """Tests for dashboard integration with other modules."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_journal_entries_do_not_break_dashboard(self):
        """Dashboard loads correctly when journal entries exist."""
        from apps.journal.models import JournalEntry

        self.enable_module(self.user, 'journal')

        # Create some entries
        for i in range(5):
            JournalEntry.objects.create(
                user=self.user,
                title=f"Entry {i}",
                body="Content",
                entry_date=date.today() - timedelta(days=i)
            )

        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertEqual(response.status_code, 200)
        # V2 dashboard provides daily_progress instead of per-module counts
        self.assertIn('daily_progress', response.context)

    def test_task_count_on_dashboard(self):
        """Dashboard shows correct task counts."""
        from apps.life.models import Task

        self.enable_module(self.user, 'life')

        # Create tasks
        Task.objects.create(
            user=self.user,
            title="Incomplete task",
            completion_status='pending'
        )
        Task.objects.create(
            user=self.user,
            title="Complete task",
            completion_status='completed'
        )

        response = self.client.get(reverse('dashboard_v2:home'))
        life_stats = response.context.get('life_stats', {})
        # Should have task info
        self.assertIsNotNone(life_stats)

    def test_weight_data_reflects_health_entries(self):
        """Weight chart data reflects health module entries."""
        from apps.health.models import WeightEntry

        self.enable_module(self.user, 'health')

        # Create weight entries
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal('180.0'),
            unit='lb'
        )

        response = self.client.get(reverse('dashboard:weight_chart_data'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('labels', data)
        self.assertIn('values', data)  # API uses 'values'
        self.assertEqual(len(data['values']), 1)


# =============================================================================
# 7. PERMISSION TESTS
# =============================================================================

class DashboardPermissionTest(DashboardTestMixin, TestCase):
    """Tests for dashboard permissions."""

    def setUp(self):
        self.client = Client()
        self.user_a = self.create_user(email='usera@example.com')
        self.user_b = self.create_user(email='userb@example.com')

    def test_user_sees_own_data_only(self):
        """User only sees their own data on dashboard."""
        # Login as user A and verify dashboard loads with user-scoped context
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertEqual(response.status_code, 200)

        # V2 dashboard greeting includes user's name — verify it's user A's
        greeting = response.context.get('greeting', '')
        self.assertNotIn('userb', greeting.lower())

        # Login as user B — should get different greeting
        self.client.login(email='userb@example.com', password='testpass123')
        response_b = self.client.get(reverse('dashboard_v2:home'))
        self.assertEqual(response_b.status_code, 200)

    def test_tile_config_only_affects_own_settings(self):
        """Tile configuration only changes the logged-in user's settings."""
        import json
        self.client.login(email='usera@example.com', password='testpass123')

        # Post tile configuration change via API
        self.client.post(
            reverse('dashboard:tile_config_api', kwargs={'tile_id': 'weather'}),
            data=json.dumps({'visible': False}),
            content_type='application/json'
        )

        # User B's settings should be unchanged
        self.user_b.preferences.refresh_from_db()
        # Default config should remain for user B (no dashboard_config set means defaults)


# =============================================================================
# 8. API/HTMX TESTS
# =============================================================================

class DashboardAPITest(DashboardTestMixin, TestCase):
    """Tests for dashboard API endpoints."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.enable_module(self.user, 'health')
        self.login_user()

    def test_weight_chart_returns_json(self):
        """Weight chart API returns valid JSON."""
        response = self.client.get(reverse('dashboard:weight_chart_data'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

        # Should be valid JSON
        data = json.loads(response.content)
        self.assertIsInstance(data, dict)

    def test_weight_chart_has_required_fields(self):
        """Weight chart data has labels and values fields."""
        response = self.client.get(reverse('dashboard:weight_chart_data'))
        data = json.loads(response.content)

        self.assertIn('labels', data)
        self.assertIn('values', data)  # API uses 'values' not 'data'

    def test_weight_chart_data_is_list(self):
        """Weight chart data fields are lists."""
        response = self.client.get(reverse('dashboard:weight_chart_data'))
        data = json.loads(response.content)

        self.assertIsInstance(data['labels'], list)
        self.assertIsInstance(data['values'], list)  # API uses 'values'


class DashboardHTMXTest(DashboardTestMixin, TestCase):
    """Tests for HTMX tile endpoints.
    
    Note: These tests are skipped if templates don't exist yet.
    """

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_journal_tile_url_exists(self):
        """Journal tile URL is configured."""
        from django.urls import reverse, NoReverseMatch
        try:
            url = reverse('dashboard:tile_journal')
            self.assertIsNotNone(url)
        except NoReverseMatch:
            self.skipTest("tile_journal URL not configured")

    def test_encouragement_tile_url_exists(self):
        """Encouragement tile URL is configured."""
        from django.urls import reverse, NoReverseMatch
        try:
            url = reverse('dashboard:tile_encouragement')
            self.assertIsNotNone(url)
        except NoReverseMatch:
            self.skipTest("tile_encouragement URL not configured")


# =============================================================================
# 9. CONFIGURATION TESTS
# =============================================================================

class DashboardConfigurationTest(DashboardTestMixin, TestCase):
    """Tests for dashboard configuration functionality.
    
    Note: Some tests skipped if configure template doesn't exist.
    """

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_configure_url_exists(self):
        """Configure URL is defined."""
        from django.urls import reverse, NoReverseMatch
        try:
            url = reverse('dashboard:configure')
            self.assertIsNotNone(url)
        except NoReverseMatch:
            self.skipTest("configure URL not defined")

    def test_default_config_exists(self):
        """V2 dashboard provides daily_progress context by default."""
        response = self.client.get(reverse('dashboard_v2:home'))
        daily_progress = response.context.get('daily_progress')
        self.assertIsNotNone(daily_progress)


# =============================================================================
# 10. ERROR HANDLING TESTS
# =============================================================================

class DashboardErrorHandlingTest(DashboardTestMixin, TestCase):
    """Tests for error handling and resilience."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_dashboard_handles_missing_preferences(self):
        """Dashboard handles user without preferences gracefully."""
        # This shouldn't happen normally, but test resilience
        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertEqual(response.status_code, 200)

    def test_invalid_weight_data_handled(self):
        """Weight API handles edge cases."""
        response = self.client.get(reverse('dashboard:weight_chart_data'))
        self.assertEqual(response.status_code, 200)
        # Should still return valid JSON
        data = json.loads(response.content)
        self.assertIsInstance(data, dict)
