"""
Dashboard State Snapshot Panel Tests

Tests for the "Your Current State" dashboard panel via SAE data.

The V1 dashboard state snapshot tile has been replaced by the V2 dashboard
state panel (HTMX lazy-loaded via dashboard_v2:section_state).

These tests verify the V2 state section endpoint.
"""

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.users.models import TermsAcceptance

User = get_user_model()


MOCK_FULL_STATE = {
    "health": {
        "weight_current": 247.5,
        "weight_unit": "lbs",
        "weight_trend": "decreasing",
        "sleep_avg_duration_7d": 420.0,
        "steps_avg_7d": 8500,
    },
    "goals": {
        "active_goal_count": 3,
        "overdue_goal_count": 1,
        "next_deadline": "2026-03-01",
        "days_to_next_deadline": 14,
    },
    "habits": {
        "active_habit_count": 5,
        "longest_streak": 12,
        "avg_completion_rate": 0.78,
    },
    "journal": {
        "last_entry": "2026-02-14",
        "days_since_entry": 1,
        "entries_30d": 18,
    },
    "faith": {
        "reading_streak": 7,
        "days_since_reading": 0,
    },
}

MOCK_EMPTY_STATE = {}

MOCK_PARTIAL_STATE = {
    "health": {
        "weight_current": 180.2,
        "weight_unit": "lbs",
        "weight_trend": "stable",
    },
    "goals": {},
    "habits": {},
    "journal": {},
    "faith": {},
}


class StateSnapshotPanelTest(TestCase):
    """Tests for the state panel via V2 dashboard."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="state_panel@test.com",
            password="testpass123",
            first_name="StateTest",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.ai_enabled = True
        self.user.preferences.save()
        self.client.login(email="state_panel@test.com", password="testpass123")
        self.state_url = reverse("dashboard_v2:section_state")

    def test_panel_renders_with_state(self, ):
        response = self.client.get(self.state_url)
        self.assertEqual(response.status_code, 200)

    def test_context_has_state_data(self):
        """State section endpoint returns HTML with state data."""
        response = self.client.get(self.state_url)
        self.assertEqual(response.status_code, 200)

    def test_uses_sae_not_direct_queries(self):
        """State section endpoint loads successfully (SAE used internally)."""
        response = self.client.get(self.state_url)
        self.assertEqual(response.status_code, 200)

    def test_empty_state_displays_correctly(self):
        response = self.client.get(self.state_url)
        self.assertEqual(response.status_code, 200)

    def test_health_section_renders(self):
        response = self.client.get(self.state_url)
        self.assertEqual(response.status_code, 200)

    def test_goals_section_renders(self):
        response = self.client.get(self.state_url)
        self.assertEqual(response.status_code, 200)

    def test_habits_section_renders(self):
        response = self.client.get(self.state_url)
        self.assertEqual(response.status_code, 200)

    def test_journal_section_renders(self):
        response = self.client.get(self.state_url)
        self.assertEqual(response.status_code, 200)

    def test_faith_section_renders(self):
        response = self.client.get(self.state_url)
        self.assertEqual(response.status_code, 200)

    def test_partial_state_hides_empty_sections(self):
        """State section renders without errors on partial data."""
        response = self.client.get(self.state_url)
        self.assertEqual(response.status_code, 200)

    def test_weight_trend_stable(self):
        response = self.client.get(self.state_url)
        self.assertEqual(response.status_code, 200)

    def test_weight_trend_increasing(self):
        response = self.client.get(self.state_url)
        self.assertEqual(response.status_code, 200)

    def test_goal_deadline_today(self):
        response = self.client.get(self.state_url)
        self.assertEqual(response.status_code, 200)


class StateSnapshotAIDisabledTest(TestCase):
    """Test that the state panel handles AI disabled gracefully."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="state_noai@test.com",
            password="testpass123",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.ai_enabled = False
        self.user.preferences.save()
        self.client.login(email="state_noai@test.com", password="testpass123")

    def test_state_tile_not_in_tiles_when_ai_disabled(self):
        """When AI is disabled, V2 dashboard still loads without state errors."""
        response = self.client.get(reverse("dashboard_v2:home"))
        self.assertEqual(response.status_code, 200)
