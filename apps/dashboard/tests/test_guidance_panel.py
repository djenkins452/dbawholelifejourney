"""
Dashboard Guidance Panel Tests

Tests for guidance items surfaced on the V2 dashboard (via HTMX insights
section) and guidance lifecycle actions.

Covers:
- Insights section renders when guidance items exist
- Insights section hidden when no items
- Guidance items display title/message in insights section
- Action endpoints (dismiss/snooze/acted) work
- Permissions: user cannot act on another user's guidance
- Deduplication & supersession logic (tested via get_active_guidance)
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.ai_guidance.models import GuidanceItem, build_guidance_dedupe_key
from apps.users.models import TermsAcceptance

User = get_user_model()


class GuidancePanelTestMixin:
    """Common setup for guidance panel tests."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="guidance_panel@test.com",
            password="testpass123",
            first_name="PanelTest",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.ai_enabled = True
        self.user.preferences.save()

        self.client.login(email="guidance_panel@test.com", password="testpass123")

    def _create_guidance(self, **kwargs):
        """Create a guidance item with defaults."""
        defaults = {
            "user": self.user,
            "title": "Test Guidance",
            "message": "This is a test guidance message.",
            "priority": 3,
            "guidance_type": "test_rule",
            "source": "sae_state",
            "module": "health",
            "dedupe_key": build_guidance_dedupe_key(
                self.user.id, "test_rule", timezone.now().isoformat()
            ),
        }
        defaults.update(kwargs)
        return GuidanceItem.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Insights Section Rendering Tests (V2 HTMX endpoint)
# ---------------------------------------------------------------------------


class GuidancePanelRenderTest(GuidancePanelTestMixin, TestCase):
    """Tests that guidance renders correctly in the V2 insights section."""

    def _get_insights(self):
        """Fetch the HTMX insights section endpoint."""
        return self.client.get(reverse("dashboard_v2:section_insights"))

    def test_panel_renders_with_items(self):
        """Insights section shows guidance when items exist."""
        self._create_guidance(title="Weight Trend Alert")
        response = self._get_insights()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Insights")
        self.assertContains(response, "Weight Trend Alert")

    def test_panel_shows_empty_state(self):
        """Insights section is empty when no guidance items."""
        response = self._get_insights()
        self.assertEqual(response.status_code, 200)
        # V2 insights section simply doesn't render when empty
        self.assertNotContains(response, "Insights")

    def test_panel_hidden_when_ai_disabled(self):
        """Guidance tile is not rendered when AI is disabled."""
        self.user.preferences.ai_enabled = False
        self.user.preferences.save()
        self._create_guidance(title="Should Not Show")
        response = self.client.get(reverse("dashboard_v2:home"))
        self.assertEqual(response.status_code, 200)
        # V2 main dashboard doesn't inline guidance content
        self.assertNotContains(response, "Should Not Show")

    def test_insights_context_limits_to_two_items(self):
        """V2 insights section limits guidance to 2 items."""
        for i in range(5):
            self._create_guidance(
                title=f"Guidance {i}",
                guidance_type=f"test_rule_{i}",
                dedupe_key=build_guidance_dedupe_key(
                    self.user.id, "test", str(i)
                ),
            )
        response = self._get_insights()
        self.assertEqual(response.status_code, 200)
        # V2 insights shows max 2 guidance items
        self.assertEqual(len(response.context["guidance_items"]), 2)

    def test_panel_excludes_dismissed_items(self):
        """Dismissed items should not appear in the insights section."""
        item = self._create_guidance(title="Dismissed Item")
        item.dismiss()
        response = self._get_insights()
        self.assertNotContains(response, "Dismissed Item")

    def test_panel_excludes_snoozed_items(self):
        """Snoozed items should not appear in the insights section."""
        item = self._create_guidance(title="Snoozed Item")
        item.snooze(timezone.now() + timedelta(hours=24))
        response = self._get_insights()
        self.assertNotContains(response, "Snoozed Item")

    def test_panel_shows_source_badge_insight(self):
        """Insight items render in the insights section."""
        self._create_guidance(source="pie_insight", title="Insight Guidance")
        response = self._get_insights()
        self.assertContains(response, "Insight Guidance")

    def test_context_contains_guidance_items(self):
        """Insights section context includes guidance_items list."""
        self._create_guidance()
        response = self._get_insights()
        self.assertIn("guidance_items", response.context)
        self.assertEqual(len(response.context["guidance_items"]), 1)


# ---------------------------------------------------------------------------
# Action Handler Tests (from Dashboard)
# ---------------------------------------------------------------------------


class GuidancePanelActionTest(GuidancePanelTestMixin, TestCase):
    """Tests for guidance lifecycle actions triggered from the dashboard."""

    def test_dismiss_action(self):
        """Dismiss action deactivates the item."""
        item = self._create_guidance()
        response = self.client.post(
            reverse("ai_guidance:action", kwargs={"pk": item.pk}),
            {"action": "dismiss"},
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertTrue(item.is_dismissed)
        self.assertFalse(item.is_active)

    def test_snooze_action(self):
        """Snooze action sets snoozed_until."""
        item = self._create_guidance()
        response = self.client.post(
            reverse("ai_guidance:action", kwargs={"pk": item.pk}),
            {"action": "snooze", "hours": "24"},
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertTrue(item.is_snoozed)
        self.assertIsNotNone(item.snoozed_until)

    def test_acted_action(self):
        """Acted action marks item as acted upon."""
        item = self._create_guidance()
        response = self.client.post(
            reverse("ai_guidance:action", kwargs={"pk": item.pk}),
            {"action": "acted"},
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertTrue(item.is_acted_upon)

    def test_read_action(self):
        """Read action marks item as read."""
        item = self._create_guidance()
        response = self.client.post(
            reverse("ai_guidance:action", kwargs={"pk": item.pk}),
            {"action": "read"},
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertTrue(item.is_read)

    def test_dismissed_item_removed_from_insights(self):
        """After dismissing, item no longer appears in insights section."""
        item = self._create_guidance(title="Will Be Dismissed")
        self.client.post(
            reverse("ai_guidance:action", kwargs={"pk": item.pk}),
            {"action": "dismiss"},
        )
        response = self.client.get(reverse("dashboard_v2:section_insights"))
        self.assertNotContains(response, "Will Be Dismissed")

    def test_snoozed_item_removed_from_insights(self):
        """After snoozing, item no longer appears in insights section."""
        item = self._create_guidance(title="Will Be Snoozed")
        self.client.post(
            reverse("ai_guidance:action", kwargs={"pk": item.pk}),
            {"action": "snooze", "hours": "24"},
        )
        response = self.client.get(reverse("dashboard_v2:section_insights"))
        self.assertNotContains(response, "Will Be Snoozed")


# ---------------------------------------------------------------------------
# Permission Tests
# ---------------------------------------------------------------------------


class GuidancePanelPermissionTest(GuidancePanelTestMixin, TestCase):
    """Tests that users cannot act on another user's guidance."""

    def test_cannot_act_on_other_users_guidance(self):
        """User cannot dismiss another user's guidance item."""
        other_user = User.objects.create_user(
            email="other@test.com",
            password="testpass123",
        )
        TermsAcceptance.objects.create(
            user=other_user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        other_item = GuidanceItem.objects.create(
            user=other_user,
            title="Other User Guidance",
            message="Not yours.",
            priority=3,
            guidance_type="test_rule",
            source="sae_state",
            dedupe_key=build_guidance_dedupe_key(other_user.id, "test", "other"),
        )
        response = self.client.post(
            reverse("ai_guidance:action", kwargs={"pk": other_item.pk}),
            {"action": "dismiss"},
        )
        self.assertEqual(response.status_code, 404)
        other_item.refresh_from_db()
        self.assertFalse(other_item.is_dismissed)

    def test_other_users_items_not_in_insights(self):
        """Other user's guidance items don't appear in current user's insights."""
        other_user = User.objects.create_user(
            email="other2@test.com",
            password="testpass123",
        )
        GuidanceItem.objects.create(
            user=other_user,
            title="Not My Guidance",
            message="Belongs to someone else.",
            priority=3,
            guidance_type="test_rule",
            source="sae_state",
            dedupe_key=build_guidance_dedupe_key(other_user.id, "test", "x"),
        )
        response = self.client.get(reverse("dashboard_v2:section_insights"))
        self.assertNotContains(response, "Not My Guidance")


# ---------------------------------------------------------------------------
# Deduplication & Supersession Tests (business logic via get_active_guidance)
# ---------------------------------------------------------------------------


class GuidancePanelDeduplicationTest(GuidancePanelTestMixin, TestCase):
    """Tests that duplicate and contradictory guidance items are filtered.

    These tests exercise get_active_guidance() directly since the dedup and
    supersession logic is independent of any view layer.
    """

    def _get_active_items(self, limit=5):
        """Call get_active_guidance directly."""
        from apps.core.ai_guidance.guidance_engine import get_active_guidance

        return get_active_guidance(self.user, limit=limit)

    def test_only_newest_per_guidance_type_and_module(self):
        """When multiple items share the same guidance_type + module, only
        the newest one (by created_at) appears."""
        # Older weight trend (created first)
        self._create_guidance(
            title="Weight trending down (-7.0 lb)",
            guidance_type="health_trend",
            module="health",
            source="pie_insight",
            priority=4,
            dedupe_key=build_guidance_dedupe_key(
                self.user.id, "health_trend", "old"
            ),
        )
        # Newer weight trend (created second — higher id, newer created_at)
        self._create_guidance(
            title="Weight trending down (-2.4 lb)",
            guidance_type="health_trend",
            module="health",
            source="pie_insight",
            priority=4,
            dedupe_key=build_guidance_dedupe_key(
                self.user.id, "health_trend", "new"
            ),
        )
        items = self._get_active_items()

        health_trend_items = [
            i for i in items if i.guidance_type == "health_trend"
        ]
        self.assertEqual(len(health_trend_items), 1)
        # The newest one wins (ordered by priority then -created_at)
        self.assertIn("-2.4", health_trend_items[0].title)

    def test_different_types_in_same_module_both_shown(self):
        """Items with different guidance_types in the same module are both kept."""
        self._create_guidance(
            title="Health trend item",
            guidance_type="health_trend",
            module="health",
            dedupe_key=build_guidance_dedupe_key(
                self.user.id, "health_trend", "a"
            ),
        )
        self._create_guidance(
            title="Health prediction",
            guidance_type="goal_risk",
            module="health",
            dedupe_key=build_guidance_dedupe_key(
                self.user.id, "goal_risk", "b"
            ),
        )
        items = self._get_active_items()
        self.assertEqual(len(items), 2)

    def test_same_type_different_module_both_shown(self):
        """Items with the same guidance_type but different modules are both kept."""
        self._create_guidance(
            title="Health reinforcement",
            guidance_type="positive_reinforcement",
            module="health",
            dedupe_key=build_guidance_dedupe_key(
                self.user.id, "positive", "health"
            ),
        )
        self._create_guidance(
            title="Journal reinforcement",
            guidance_type="positive_reinforcement",
            module="journal",
            dedupe_key=build_guidance_dedupe_key(
                self.user.id, "positive", "journal"
            ),
        )
        items = self._get_active_items()
        self.assertEqual(len(items), 2)

    def test_supersession_journal_streak_hides_inactivity(self):
        """A journal positive_reinforcement item should supersede a
        journal_inactivity item for the same module."""
        # Older inactivity guidance
        self._create_guidance(
            title="You haven't journaled recently",
            guidance_type="journal_inactivity",
            module="journal",
            source="sae_state",
            priority=5,
            dedupe_key=build_guidance_dedupe_key(
                self.user.id, "journal_zero_30d"
            ),
        )
        # Newer positive reinforcement (journaling streak)
        self._create_guidance(
            title="4-day journaling streak!",
            guidance_type="positive_reinforcement",
            module="journal",
            source="pie_insight",
            priority=4,
            dedupe_key=build_guidance_dedupe_key(
                self.user.id, "positive", "streak"
            ),
        )
        items = self._get_active_items()

        titles = [i.title for i in items]
        self.assertIn("4-day journaling streak!", titles)
        self.assertNotIn("You haven't journaled recently", titles)

    def test_supersession_only_applies_within_same_module(self):
        """Supersession should NOT cross module boundaries."""
        # Journal inactivity
        self._create_guidance(
            title="You haven't journaled recently",
            guidance_type="journal_inactivity",
            module="journal",
            priority=5,
            dedupe_key=build_guidance_dedupe_key(
                self.user.id, "journal_zero_30d"
            ),
        )
        # Health positive reinforcement (different module)
        self._create_guidance(
            title="Weight trending down",
            guidance_type="positive_reinforcement",
            module="health",
            priority=4,
            dedupe_key=build_guidance_dedupe_key(
                self.user.id, "positive", "health"
            ),
        )
        items = self._get_active_items()
        titles = [i.title for i in items]
        # Both should be present — different modules
        self.assertIn("You haven't journaled recently", titles)
        self.assertIn("Weight trending down", titles)

    def test_no_supersession_when_only_inactivity_exists(self):
        """If only the inactivity item exists (no superseding item),
        it should still be shown."""
        self._create_guidance(
            title="You haven't journaled recently",
            guidance_type="journal_inactivity",
            module="journal",
            priority=5,
            dedupe_key=build_guidance_dedupe_key(
                self.user.id, "journal_zero_30d"
            ),
        )
        items = self._get_active_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "You haven't journaled recently")
