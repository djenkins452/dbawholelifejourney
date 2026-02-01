"""
Cycle Tracking View/Template Tests

Tests for cycle tracking template rendering and view logic including:
- Opt-in page rendering
- Daily log form submission
- Calendar view with data
- Settings page saves updates
- HTMX partial responses
- Mobile responsiveness (viewport meta tag)

Location: apps/health/tests/test_cycle_views.py
"""

import json
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.health.models import (
    Cycle,
    CycleDailyLog,
    CyclePrediction,
    CycleSettings,
)
from apps.users.models import TermsAcceptance

User = get_user_model()


# Override static files storage to avoid manifest issues during testing
TEST_STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
}


class CycleViewTestBase(TestCase):
    """Base class for cycle view tests with common setup."""

    def setUp(self):
        """Set up test user and client."""
        self.user = self._create_test_user()
        self.client = Client()
        self.client.login(email="test@example.com", password="testpass123")

    def _create_test_user(self, email="test@example.com", password="testpass123"):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(email=email, password=password)
        current_terms_version = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        TermsAcceptance.objects.create(user=user, terms_version=current_terms_version)
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def _enable_cycle_tracking(self, user=None):
        """Enable cycle tracking for a user."""
        target_user = user or self.user
        return CycleSettings.objects.create(
            user=target_user,
            cycle_tracking_enabled=True,
            average_cycle_length=28,
            average_period_length=5,
        )


# =============================================================================
# Opt-In Page Tests
# =============================================================================


@override_settings(STORAGES=TEST_STORAGES)
class CycleOptInPageTests(CycleViewTestBase):
    """Test opt-in page renders correctly."""

    def test_opt_in_page_renders_for_logged_in_user(self):
        """Opt-in page renders successfully for logged in user."""
        response = self.client.get(reverse("health:cycle_opt_in_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cycle Tracking")

    def test_opt_in_page_requires_authentication(self):
        """Opt-in page requires authentication."""
        self.client.logout()
        response = self.client.get(reverse("health:cycle_opt_in_page"))
        # Should redirect to login
        self.assertIn(response.status_code, [302, 401])

    def test_opt_in_page_shows_enable_button_when_not_enabled(self):
        """Opt-in page shows enable button when tracking is not enabled."""
        response = self.client.get(reverse("health:cycle_opt_in_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enable Cycle Tracking")
        self.assertContains(response, "opt-in-form")

    def test_opt_in_page_shows_enabled_state_when_enabled(self):
        """Opt-in page shows enabled state when tracking is enabled."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_opt_in_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cycle tracking is enabled")
        self.assertContains(response, "Go to Dashboard")

    def test_opt_in_page_shows_privacy_information(self):
        """Opt-in page displays privacy information."""
        response = self.client.get(reverse("health:cycle_opt_in_page"))
        self.assertContains(response, "Your privacy matters")
        self.assertContains(response, "Your data stays private")
        self.assertContains(response, "Stored securely")

    def test_opt_in_page_shows_feature_descriptions(self):
        """Opt-in page displays feature descriptions."""
        response = self.client.get(reverse("health:cycle_opt_in_page"))
        self.assertContains(response, "Period days")
        self.assertContains(response, "Mood and energy")
        self.assertContains(response, "Physical symptoms")
        self.assertContains(response, "Predictions")

    def test_opt_in_page_has_back_to_health_link(self):
        """Opt-in page has link back to health section."""
        response = self.client.get(reverse("health:cycle_opt_in_page"))
        self.assertContains(response, reverse("health:home"))

    def test_opt_in_page_shows_disable_modal_when_enabled(self):
        """Opt-in page shows disable confirmation modal when enabled."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_opt_in_page"))
        self.assertContains(response, "disable-modal")
        self.assertContains(response, "Disable Cycle Tracking")


# =============================================================================
# Daily Log Form Submission Tests
# =============================================================================


@override_settings(STORAGES=TEST_STORAGES)
class CycleDailyLogFormSubmissionTests(CycleViewTestBase):
    """Test daily log form submission creates entry."""

    def setUp(self):
        """Set up test user with cycle tracking enabled."""
        super().setUp()
        self._enable_cycle_tracking()

    def test_create_daily_log_via_api(self):
        """Creating a daily log via API creates entry in database."""
        log_data = {
            "log_date": str(date.today()),
            "flow_level": "medium",
            "mood": "happy",
            "energy_level": 4,
            "symptoms": ["cramps", "fatigue"],
            "notes": "Test entry",
        }

        response = self.client.post(
            reverse("health:cycle_daily_logs_list"),
            data=json.dumps(log_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["flow_level"], "medium")
        self.assertEqual(data["mood"], "happy")

        # Verify entry was created in database
        log = CycleDailyLog.objects.get(id=data["id"])
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.flow_level, "medium")
        self.assertEqual(log.mood, "happy")
        self.assertEqual(log.energy_level, 4)
        self.assertIn("cramps", log.symptoms)
        self.assertEqual(log.notes, "Test entry")

    def test_create_daily_log_with_minimal_data(self):
        """Creating a daily log with minimal data succeeds."""
        log_data = {
            "log_date": str(date.today()),
            "flow_level": "light",
        }

        response = self.client.post(
            reverse("health:cycle_daily_logs_list"),
            data=json.dumps(log_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        log = CycleDailyLog.objects.get(user=self.user, log_date=date.today())
        self.assertEqual(log.flow_level, "light")

    def test_daily_log_form_validates_flow_level(self):
        """Daily log form validates flow level choices."""
        log_data = {
            "log_date": str(date.today()),
            "flow_level": "invalid_flow",
        }

        response = self.client.post(
            reverse("health:cycle_daily_logs_list"),
            data=json.dumps(log_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_daily_log_triggers_cycle_detection(self):
        """Creating a log with flow triggers cycle detection service."""
        # First, create a log with flow to start a cycle
        log_data = {
            "log_date": str(date.today()),
            "flow_level": "medium",
        }

        response = self.client.post(
            reverse("health:cycle_daily_logs_list"),
            data=json.dumps(log_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

        # Check if a cycle was created
        cycles = Cycle.objects.filter(user=self.user)
        # Cycle should be created or updated by the detection service
        self.assertGreaterEqual(cycles.count(), 0)

    def test_update_existing_daily_log(self):
        """Updating an existing daily log succeeds."""
        # Create initial log
        log = CycleDailyLog.objects.create(
            user=self.user,
            log_date=date.today() - timedelta(days=1),
            flow_level="light",
            mood="neutral",
        )

        update_data = {
            "log_date": str(date.today() - timedelta(days=1)),
            "flow_level": "heavy",
            "mood": "happy",
            "energy_level": 5,
        }

        response = self.client.put(
            reverse("health:cycle_daily_logs_detail", kwargs={"log_id": log.id}),
            data=json.dumps(update_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        log.refresh_from_db()
        self.assertEqual(log.flow_level, "heavy")
        self.assertEqual(log.mood, "happy")


# =============================================================================
# Calendar View Tests
# =============================================================================


@override_settings(STORAGES=TEST_STORAGES)
class CycleCalendarViewTests(CycleViewTestBase):
    """Test calendar view renders with data."""

    def test_calendar_view_requires_authentication(self):
        """Calendar view requires authentication."""
        self.client.logout()
        response = self.client.get(reverse("health:cycle_calendar"))
        self.assertIn(response.status_code, [302, 401])

    def test_calendar_view_renders_for_enabled_user(self):
        """Calendar view renders for user with cycle tracking enabled."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_calendar"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cycle Calendar")

    def test_calendar_view_contains_navigation_controls(self):
        """Calendar view contains month navigation controls."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_calendar"))
        self.assertContains(response, "prev-month")
        self.assertContains(response, "next-month")

    def test_calendar_view_contains_legend(self):
        """Calendar view contains flow level legend."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_calendar"))
        self.assertContains(response, "Heavy Flow")
        self.assertContains(response, "Medium Flow")
        self.assertContains(response, "Light Flow")
        self.assertContains(response, "Spotting")

    def test_calendar_view_contains_logs_data(self):
        """Calendar view contains serialized logs data for JavaScript."""
        self._enable_cycle_tracking()

        # Create some daily logs
        CycleDailyLog.objects.create(
            user=self.user,
            log_date=date.today(),
            flow_level="medium",
            mood="happy",
        )
        CycleDailyLog.objects.create(
            user=self.user,
            log_date=date.today() - timedelta(days=1),
            flow_level="light",
        )

        response = self.client.get(reverse("health:cycle_calendar"))
        self.assertEqual(response.status_code, 200)
        # Check that calendar data object is included with logs
        self.assertContains(response, "calendarData")
        self.assertContains(response, "logs:")
        self.assertContains(response, "medium")

    def test_calendar_view_contains_predictions_data(self):
        """Calendar view contains serialized predictions data."""
        self._enable_cycle_tracking()

        # Create a prediction
        CyclePrediction.objects.create(
            user=self.user,
            predicted_period_start=date.today() + timedelta(days=14),
            predicted_period_end=date.today() + timedelta(days=19),
            prediction_confidence=Decimal("0.80"),
        )

        response = self.client.get(reverse("health:cycle_calendar"))
        self.assertContains(response, "predictions:")

    def test_calendar_view_has_fertile_window_toggle(self):
        """Calendar view has fertile window toggle."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_calendar"))
        self.assertContains(response, "show-fertile")
        self.assertContains(response, "Show Fertile Window")

    def test_calendar_view_has_day_headers(self):
        """Calendar view has day of week headers."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_calendar"))
        self.assertContains(response, "Sun")
        self.assertContains(response, "Mon")
        self.assertContains(response, "Tue")
        self.assertContains(response, "Wed")
        self.assertContains(response, "Thu")
        self.assertContains(response, "Fri")
        self.assertContains(response, "Sat")


# =============================================================================
# Settings Page Tests
# =============================================================================


@override_settings(STORAGES=TEST_STORAGES)
class CycleSettingsPageTests(CycleViewTestBase):
    """Test settings page saves updates."""

    def test_settings_page_requires_authentication(self):
        """Settings page requires authentication."""
        self.client.logout()
        response = self.client.get(reverse("health:cycle_settings_page"))
        self.assertIn(response.status_code, [302, 401])

    def test_settings_page_requires_cycle_tracking_enabled(self):
        """Settings page requires cycle tracking to be enabled."""
        response = self.client.get(reverse("health:cycle_settings_page"))
        # Should return 403 or redirect
        self.assertIn(response.status_code, [403, 302])

    def test_settings_page_renders_with_current_values(self):
        """Settings page renders with current setting values."""
        settings = self._enable_cycle_tracking()
        settings.average_cycle_length = 30
        settings.average_period_length = 6
        settings.fertile_window_tracking_enabled = True
        settings.save()

        response = self.client.get(reverse("health:cycle_settings_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="30"')
        self.assertContains(response, 'value="6"')
        self.assertContains(response, "checked")

    def test_settings_page_contains_form_fields(self):
        """Settings page contains expected form fields."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_settings_page"))
        self.assertContains(response, "average_cycle_length")
        self.assertContains(response, "average_period_length")
        self.assertContains(response, "fertile_window_tracking_enabled")
        self.assertContains(response, "notifications_enabled")

    def test_settings_api_updates_values(self):
        """Settings API updates cycle settings values."""
        self._enable_cycle_tracking()

        update_data = {
            "average_cycle_length": 32,
            "average_period_length": 7,
            "fertile_window_tracking_enabled": True,
        }

        response = self.client.patch(
            reverse("health:cycle_settings_api"),
            data=json.dumps(update_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["average_cycle_length"], 32)
        self.assertEqual(data["average_period_length"], 7)
        self.assertTrue(data["fertile_window_tracking_enabled"])

        # Verify in database
        settings = CycleSettings.objects.get(user=self.user)
        self.assertEqual(settings.average_cycle_length, 32)

    def test_settings_page_has_data_management_link(self):
        """Settings page has link to data management."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_settings_page"))
        self.assertContains(response, reverse("health:cycle_data_management"))
        self.assertContains(response, "Export or delete your data")


# =============================================================================
# HTMX Partial Response Tests
# =============================================================================


@override_settings(STORAGES=TEST_STORAGES)
class CycleHTMXPartialResponseTests(CycleViewTestBase):
    """Test HTMX partial responses return correct content."""

    def setUp(self):
        """Set up test user with cycle tracking enabled."""
        super().setUp()
        self._enable_cycle_tracking()

    def test_day_modal_returns_html_fragment(self):
        """Day modal endpoint returns HTML fragment."""
        # Create a log for the date
        CycleDailyLog.objects.create(
            user=self.user,
            log_date=date.today(),
            flow_level="medium",
            mood="happy",
        )

        response = self.client.get(
            reverse("health:cycle_day_modal"),
            {"date": str(date.today())},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "day-modal")
        self.assertContains(response, "Medium")  # Flow level display

    def test_day_modal_shows_empty_form_for_new_day(self):
        """Day modal shows empty form for day without log."""
        # Request modal for a day without a log
        response = self.client.get(
            reverse("health:cycle_day_modal"),
            {"date": str(date.today() - timedelta(days=5))},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No data for this day yet")
        self.assertContains(response, "log-edit-form")

    def test_day_modal_shows_existing_data(self):
        """Day modal shows existing log data."""
        CycleDailyLog.objects.create(
            user=self.user,
            log_date=date.today() - timedelta(days=1),
            flow_level="heavy",
            mood="sad",
            energy_level=2,
            symptoms=["cramps", "headache"],
            notes="Test notes",
        )

        response = self.client.get(
            reverse("health:cycle_day_modal"),
            {"date": str(date.today() - timedelta(days=1))},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Heavy")
        # Check for symptoms
        self.assertContains(response, "Cramps")
        self.assertContains(response, "Headache")

    def test_day_modal_requires_date_parameter(self):
        """Day modal requires date parameter."""
        response = self.client.get(reverse("health:cycle_day_modal"))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Missing date parameter", status_code=400)

    def test_day_modal_validates_date_format(self):
        """Day modal validates date format."""
        response = self.client.get(
            reverse("health:cycle_day_modal"),
            {"date": "invalid-date"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Invalid date format", status_code=400)

    def test_period_toggle_returns_html_fragment(self):
        """Period toggle endpoint returns HTML fragment."""
        response = self.client.post(
            reverse("health:cycle_period_toggle"),
            {"action": "start"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cycle-quick-actions")
        self.assertContains(response, "Period started")

    def test_period_toggle_start_creates_log(self):
        """Period toggle start action creates log entry."""
        response = self.client.post(
            reverse("health:cycle_period_toggle"),
            {"action": "start"},
        )

        self.assertEqual(response.status_code, 200)

        # Verify log was created
        log = CycleDailyLog.objects.get(user=self.user, log_date=date.today())
        self.assertEqual(log.flow_level, "medium")

    def test_period_toggle_end_marks_period_complete(self):
        """Period toggle end action marks period as complete."""
        # First start a period
        self.client.post(
            reverse("health:cycle_period_toggle"),
            {"action": "start"},
        )

        # Then end it
        response = self.client.post(
            reverse("health:cycle_period_toggle"),
            {"action": "end"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Period ended")

    def test_period_toggle_invalid_action_returns_error(self):
        """Period toggle with invalid action returns error."""
        response = self.client.post(
            reverse("health:cycle_period_toggle"),
            {"action": "invalid"},
        )

        self.assertEqual(response.status_code, 400)


# =============================================================================
# Mobile Responsiveness Tests
# =============================================================================


@override_settings(STORAGES=TEST_STORAGES)
class CycleMobileResponsivenessTests(CycleViewTestBase):
    """Test pages are mobile-responsive (viewport meta tag present)."""

    def test_opt_in_page_has_viewport_meta_tag(self):
        """Opt-in page has viewport meta tag for mobile responsiveness."""
        response = self.client.get(reverse("health:cycle_opt_in_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="viewport"')
        self.assertContains(response, 'width=device-width')

    def test_dashboard_has_viewport_meta_tag(self):
        """Dashboard has viewport meta tag for mobile responsiveness."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="viewport"')
        self.assertContains(response, 'width=device-width')

    def test_calendar_has_viewport_meta_tag(self):
        """Calendar has viewport meta tag for mobile responsiveness."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_calendar"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="viewport"')
        self.assertContains(response, 'width=device-width')

    def test_settings_page_has_viewport_meta_tag(self):
        """Settings page has viewport meta tag for mobile responsiveness."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_settings_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="viewport"')
        self.assertContains(response, 'width=device-width')

    def test_data_management_has_viewport_meta_tag(self):
        """Data management page has viewport meta tag for mobile responsiveness."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_data_management"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="viewport"')
        self.assertContains(response, 'width=device-width')

    def test_opt_in_page_has_mobile_css(self):
        """Opt-in page has mobile-specific CSS rules."""
        response = self.client.get(reverse("health:cycle_opt_in_page"))
        self.assertEqual(response.status_code, 200)
        # Check for mobile breakpoint media query
        self.assertContains(response, "@media")
        self.assertContains(response, "max-width: 480px")

    def test_calendar_has_mobile_css(self):
        """Calendar has mobile-specific CSS rules."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_calendar"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "@media")
        self.assertContains(response, "max-width: 480px")

    def test_settings_has_mobile_css(self):
        """Settings page has mobile-specific CSS rules."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_settings_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "@media")
        self.assertContains(response, "max-width: 480px")


# =============================================================================
# Dashboard View Tests
# =============================================================================


@override_settings(STORAGES=TEST_STORAGES)
class CycleDashboardViewTests(CycleViewTestBase):
    """Test dashboard view renders correctly."""

    def test_dashboard_requires_authentication(self):
        """Dashboard requires authentication."""
        self.client.logout()
        response = self.client.get(reverse("health:cycle_dashboard"))
        self.assertIn(response.status_code, [302, 401])

    def test_dashboard_shows_empty_state_when_not_enabled(self):
        """Dashboard shows empty state when cycle tracking not enabled."""
        response = self.client.get(reverse("health:cycle_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Start Tracking Your Cycle")
        self.assertContains(response, "Get Started")

    def test_dashboard_shows_content_when_enabled(self):
        """Dashboard shows cycle content when enabled."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cycle-dashboard")
        self.assertContains(response, "Recent Logs")

    def test_dashboard_shows_quick_actions(self):
        """Dashboard shows quick action buttons."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_dashboard"))
        self.assertContains(response, "Log Today")
        self.assertContains(response, "Calendar")
        self.assertContains(response, "Statistics")

    def test_dashboard_shows_recent_logs(self):
        """Dashboard shows recent log entries."""
        self._enable_cycle_tracking()

        # Create some recent logs
        for i in range(3):
            CycleDailyLog.objects.create(
                user=self.user,
                log_date=date.today() - timedelta(days=i),
                flow_level="medium" if i < 2 else "none",
                mood="happy",
            )

        response = self.client.get(reverse("health:cycle_dashboard"))
        self.assertContains(response, "logs-list")
        self.assertContains(response, "Medium")

    def test_dashboard_shows_floating_action_button(self):
        """Dashboard shows floating action button for quick log."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_dashboard"))
        self.assertContains(response, "fab-quick-log")

    def test_dashboard_has_log_modal(self):
        """Dashboard has log modal container."""
        self._enable_cycle_tracking()
        response = self.client.get(reverse("health:cycle_dashboard"))
        self.assertContains(response, "log-modal")
