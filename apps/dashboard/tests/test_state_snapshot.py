"""
Dashboard State Snapshot Panel Tests

Tests for the "Your Current State" dashboard tile that shows SAE data.

Covers:
- Panel renders when state data exists
- Empty state renders when no data
- Panel hidden when AI disabled
- Uses SAE (mocked get_user_state)
- Individual domain sections display correctly
- Domains with no data are hidden
"""

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

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
    """Tests for the state snapshot dashboard tile."""

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

    @patch("apps.core.ai_state.state_engine.get_user_state", return_value=MOCK_FULL_STATE)
    def test_panel_renders_with_state(self, mock_state):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "state-snapshot-tile")
        self.assertContains(response, "Your Current State")

    @patch("apps.core.ai_state.state_engine.get_user_state", return_value=MOCK_FULL_STATE)
    def test_context_has_user_state(self, mock_state):
        response = self.client.get("/dashboard/")
        self.assertIn("user_state", response.context)
        self.assertEqual(response.context["user_state"]["health"]["weight_current"], 247.5)

    @patch("apps.core.ai_state.state_engine.get_user_state", return_value=MOCK_FULL_STATE)
    def test_uses_sae_not_direct_queries(self, mock_state):
        """Verify get_user_state is called (SAE), not direct DB queries."""
        self.client.get("/dashboard/")
        mock_state.assert_called_once_with(self.user)

    @patch("apps.core.ai_state.state_engine.get_user_state", return_value=MOCK_EMPTY_STATE)
    def test_empty_state_displays_correctly(self, mock_state):
        response = self.client.get("/dashboard/")
        self.assertContains(response, "Start logging activity to build your state profile.")

    @patch("apps.core.ai_state.state_engine.get_user_state", return_value=MOCK_FULL_STATE)
    def test_health_section_renders(self, mock_state):
        response = self.client.get("/dashboard/")
        self.assertContains(response, "247.5")
        self.assertContains(response, "lbs")
        self.assertContains(response, "improving")
        self.assertContains(response, "7h 0m")
        self.assertContains(response, "8500")

    @patch("apps.core.ai_state.state_engine.get_user_state", return_value=MOCK_FULL_STATE)
    def test_goals_section_renders(self, mock_state):
        response = self.client.get("/dashboard/")
        self.assertContains(response, "Active Goals")
        self.assertContains(response, "Overdue")
        self.assertContains(response, "14 days")

    @patch("apps.core.ai_state.state_engine.get_user_state", return_value=MOCK_FULL_STATE)
    def test_habits_section_renders(self, mock_state):
        response = self.client.get("/dashboard/")
        self.assertContains(response, "Active Habits")
        self.assertContains(response, "12 days")

    @patch("apps.core.ai_state.state_engine.get_user_state", return_value=MOCK_FULL_STATE)
    def test_journal_section_renders(self, mock_state):
        response = self.client.get("/dashboard/")
        self.assertContains(response, "Yesterday")
        self.assertContains(response, "18")

    @patch("apps.core.ai_state.state_engine.get_user_state", return_value=MOCK_FULL_STATE)
    def test_faith_section_renders(self, mock_state):
        response = self.client.get("/dashboard/")
        self.assertContains(response, "Reading Streak")
        self.assertContains(response, "7 days")

    @patch("apps.core.ai_state.state_engine.get_user_state", return_value=MOCK_PARTIAL_STATE)
    def test_partial_state_hides_empty_sections(self, mock_state):
        """Sections with no meaningful data should not render."""
        response = self.client.get("/dashboard/")
        self.assertContains(response, "180.2")
        # Goals, habits, journal, faith sections should not render
        self.assertNotContains(response, "Active Goals")
        self.assertNotContains(response, "Active Habits")
        self.assertNotContains(response, "Entries (30d)")
        self.assertNotContains(response, "Reading Streak")

    @patch("apps.core.ai_state.state_engine.get_user_state", return_value=MOCK_FULL_STATE)
    def test_weight_trend_stable(self, mock_state):
        mock_state.return_value = {
            "health": {"weight_current": 200, "weight_unit": "lbs", "weight_trend": "stable"},
        }
        response = self.client.get("/dashboard/")
        self.assertContains(response, "stable")

    @patch("apps.core.ai_state.state_engine.get_user_state", return_value=MOCK_FULL_STATE)
    def test_weight_trend_increasing(self, mock_state):
        mock_state.return_value = {
            "health": {"weight_current": 200, "weight_unit": "lbs", "weight_trend": "increasing"},
        }
        response = self.client.get("/dashboard/")
        self.assertContains(response, "increasing")

    @patch("apps.core.ai_state.state_engine.get_user_state", return_value=MOCK_FULL_STATE)
    def test_goal_deadline_today(self, mock_state):
        mock_state.return_value = {
            "goals": {"active_goal_count": 1, "next_deadline": "2026-02-15", "days_to_next_deadline": 0},
        }
        response = self.client.get("/dashboard/")
        self.assertContains(response, "Today")


class StateSnapshotAIDisabledTest(TestCase):
    """Test that the state snapshot panel is hidden when AI is disabled."""

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
        """When AI is disabled, state_snapshot tile should not appear in visible tiles."""
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        # The tile should not be in visible tiles since it depends on ai_enabled
        tiles = response.context.get("dashboard_tiles", [])
        tile_ids = [t["id"] for t in tiles]
        self.assertNotIn("state_snapshot", tile_ids)
