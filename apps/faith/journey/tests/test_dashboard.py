"""
Tests for the Faith-dashboard Journey card and the domain capability.

Scope:
  - get_dashboard_card_data() returns None for users without an active journey
  - get_dashboard_card_data() returns the expected shape for active journeys
  - The dashboard card partial renders cleanly on the faith home page
  - The faith.journey domain capability is registered correctly
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.faith.journey.dashboard import get_dashboard_card_data
from apps.faith.journey.models import JourneyArc, JourneyPath, UserJourney


User = get_user_model()


def _make_user(email="dash@example.com"):
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class DashboardCardDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_journey_path", "walking_with_god")

    def test_returns_none_when_user_has_no_active_journey(self):
        user = _make_user("noactive@example.com")
        self.assertIsNone(get_dashboard_card_data(user))

    def test_returns_none_for_anonymous_user(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertIsNone(get_dashboard_card_data(AnonymousUser()))

    def test_returns_expected_shape_for_active_journey(self):
        user = _make_user("active@example.com")
        UserJourney.objects.create(
            user=user,
            journey_path=JourneyPath.objects.get(slug="walking_with_god"),
            current_arc=JourneyArc.objects.get(slug="creation_to_egypt"),
            current_day_number=1,
        )
        data = get_dashboard_card_data(user)
        self.assertIsNotNone(data)
        self.assertEqual(data["journey_name"], "Walking With God Through Scripture")
        self.assertEqual(data["arc_name"], "Creation to Egypt")
        self.assertEqual(data["day_number"], 1)
        self.assertEqual(data["total_days"], 7)
        # Focus is Day 1's key_insight — short, one-sentence
        self.assertIn("God", data["focus"])
        self.assertIn("Genesis 1:1-31", data["scripture_refs"])


class DashboardCardRenderTests(TestCase):
    """The journey card partial appears on the faith dashboard when applicable."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_journey_path", "walking_with_god")

    def setUp(self):
        self.user = _make_user("render@example.com")
        self.client = Client()
        self.client.force_login(self.user)

    def test_card_does_not_render_when_no_active_journey(self):
        resp = self.client.get(reverse("faith:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'data-testid="journey-dashboard-card"', resp.content)

    def test_card_renders_with_active_journey(self):
        UserJourney.objects.create(
            user=self.user,
            journey_path=JourneyPath.objects.get(slug="walking_with_god"),
            current_arc=JourneyArc.objects.get(slug="creation_to_egypt"),
            current_day_number=1,
        )
        resp = self.client.get(reverse("faith:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'data-testid="journey-dashboard-card"', resp.content)
        # Card contains the journey name, arc name, day position
        self.assertIn(b"Walking With God Through Scripture", resp.content)
        self.assertIn(b"Creation to Egypt", resp.content)
        self.assertIn(b"Day 1", resp.content)
        # Quiet language only — no urgency / guilt / streak
        body = resp.content.lower()
        # Scope the card itself for the no-pressure-language assertion.
        import re
        m = re.search(rb'<section class="journey-dashboard-card".*?</section>', resp.content, re.DOTALL)
        self.assertIsNotNone(m)
        card_html = m.group(0).lower()
        self.assertNotIn(b"streak", card_html)
        self.assertNotIn(b"behind", card_html)
        self.assertNotIn(b"missed", card_html)
        self.assertNotIn(b"don't forget", card_html)
        self.assertNotIn(b"urgent", card_html)


class CapabilityRegistrationTests(TestCase):
    """The faith.journey domain capability is registered and discoverable."""

    def test_faith_journey_capability_is_registered(self):
        from apps.core.domain_registry import registry
        cap = registry.get("faith.journey")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.name, "faith.journey")
        self.assertEqual(cap.display_name, "Walking With God Through Scripture")
        self.assertEqual(cap.url_namespace, "journey")
        # No CoS intents in Phase 1
        self.assertEqual(cap.intent_types, [])
        # Phase 1 promise: no proactive surfacing
        self.assertEqual(cap.proactive_signals, [])
        # Six signals documented (additive only — no consumers wired)
        self.assertIn("journey.started", cap.expected_signal_types)
        self.assertIn("journey.day.completed", cap.expected_signal_types)
        self.assertIn("journey.arc.completed", cap.expected_signal_types)
        self.assertIn("journey.application.committed", cap.expected_signal_types)
        self.assertIn("journey.confusion.flagged", cap.expected_signal_types)
        self.assertIn("journey.resumed", cap.expected_signal_types)

    def test_existing_faith_capability_unmodified(self):
        """Sanity: the faith domain capability still exists and is untouched."""
        from apps.core.domain_registry import registry
        cap = registry.get("faith")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.display_name, "Faith & Spiritual")
        # The existing reading-plan models remain primary for faith proper.
        self.assertIn("ReadingPlan", cap.primary_models)
