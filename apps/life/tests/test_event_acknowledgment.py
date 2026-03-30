"""
Tests for deterministic critical signal acknowledgment.

Verifies:
1. Structured critical event objects are correct
2. Acknowledgment builder generates correct text for each event type
3. Relationship priority affects wording and ordering
4. Multiple events are combined and sorted
5. Structured idempotency: keyword + person name matching
6. Injection only for unacknowledged events
7. No events = no acknowledgment
"""
import datetime

from django.conf import settings
from django.test import TestCase

from apps.users.models import User, TermsAcceptance


def _create_test_user(email="ack_test@example.com"):
    """Create a test user with required onboarding."""
    user = User.objects.create_user(
        email=email, password="testpass123",
    )
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# ═══════════════════════════════════════════════════════════════════
# Structured event objects
# ═══════════════════════════════════════════════════════════════════


class TestGetTodayCriticalEvents(TestCase):
    """Test structured critical event object generation."""

    def setUp(self):
        self.user = _create_test_user()

    def test_no_events_returns_empty_list(self):
        from apps.life.services.event_acknowledgment import (
            get_today_critical_events,
        )
        result = get_today_critical_events(self.user)
        self.assertEqual(result, [])

    def test_birthday_returns_structured_event(self):
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            get_today_critical_events,
        )

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="Mom's Birthday",
            event_type="birthday",
            event_date=today,
            person_name="Mom",
            original_year=1960,
        )

        events = get_today_critical_events(self.user)
        self.assertEqual(len(events), 1)

        ev = events[0]
        self.assertEqual(ev["type"], "birthday")
        self.assertEqual(ev["person"], "Mom")
        self.assertIn("priority", ev)
        self.assertIn("priority_rank", ev)
        self.assertIn("message", ev)
        self.assertIn("keywords", ev)
        self.assertIn("birthday", ev["keywords"])
        self.assertIn("mom", ev["keywords"])
        self.assertEqual(ev["years"], today.year - 1960)

    def test_events_sorted_by_priority(self):
        """Self events come before family events."""
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            get_today_critical_events,
        )

        today = datetime.date.today()
        # Create family event first
        SignificantEvent.objects.create(
            user=self.user,
            title="Mom's Birthday",
            event_type="birthday",
            event_date=today,
            person_name="Mom",
        )
        # Then self event
        SignificantEvent.objects.create(
            user=self.user,
            title="My Birthday",
            event_type="birthday",
            event_date=today,
            person_name="Danny",
        )

        events = get_today_critical_events(self.user)
        self.assertEqual(len(events), 2)
        # Self should be first (priority_rank=1)
        self.assertEqual(events[0]["priority"], "self")
        self.assertEqual(events[1]["priority"], "family")

    def test_future_event_not_included(self):
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            get_today_critical_events,
        )

        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        SignificantEvent.objects.create(
            user=self.user,
            title="Future Event",
            event_type="birthday",
            event_date=tomorrow,
            person_name="Someone",
        )

        events = get_today_critical_events(self.user)
        self.assertEqual(events, [])


# ═══════════════════════════════════════════════════════════════════
# Acknowledgment text generation
# ═══════════════════════════════════════════════════════════════════


class TestBuildEventAcknowledgment(TestCase):
    """Test the text acknowledgment builder."""

    def setUp(self):
        self.user = _create_test_user(email="build_ack@example.com")

    def test_no_events_returns_none(self):
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )
        result = build_event_acknowledgment(self.user)
        self.assertIsNone(result)

    def test_self_birthday(self):
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="My Birthday",
            event_type="birthday",
            event_date=today,
            person_name="Danny",
            original_year=1981,
        )

        result = build_event_acknowledgment(self.user)
        self.assertIn("Happy birthday", result)
        self.assertIn("Danny", result)

    def test_family_birthday(self):
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="Mom's Birthday",
            event_type="birthday",
            event_date=today,
            person_name="Mom",
            original_year=1960,
        )

        result = build_event_acknowledgment(self.user)
        self.assertIn("Mom", result)
        self.assertIn("birthday", result.lower())

    def test_anniversary(self):
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="Wedding Anniversary",
            event_type="anniversary",
            event_date=today,
            person_name="",
            original_year=2016,
        )

        result = build_event_acknowledgment(self.user)
        self.assertIn("anniversary", result.lower())
        years = today.year - 2016
        self.assertIn(str(years), result)

    def test_memorial(self):
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="Dad's Memorial",
            event_type="memorial",
            event_date=today,
            person_name="Dad",
        )

        result = build_event_acknowledgment(self.user)
        self.assertIn("Remembering", result)
        self.assertIn("Dad", result)

    def test_multiple_events_combined(self):
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="Mom's Birthday",
            event_type="birthday",
            event_date=today,
            person_name="Mom",
        )
        SignificantEvent.objects.create(
            user=self.user,
            title="Wedding Anniversary",
            event_type="anniversary",
            event_date=today,
            person_name="",
        )

        result = build_event_acknowledgment(self.user)
        self.assertIn("Mom", result)
        self.assertIn("anniversary", result.lower())


# ═══════════════════════════════════════════════════════════════════
# Structured idempotency (keyword + person matching)
# ═══════════════════════════════════════════════════════════════════


class TestIdempotencyCheck(TestCase):
    """Test the structured idempotency check."""

    def test_birthday_acknowledged_by_llm(self):
        """LLM says 'Happy birthday' → event is acknowledged for self."""
        from apps.life.services.event_acknowledgment import (
            check_response_acknowledges_events,
        )

        events = [{
            "type": "birthday",
            "priority": "self",
            "person": "Danny",
            "message": "Happy birthday, Danny!",
            "keywords": {"birthday", "born", "turning", "danny"},
        }]
        response = "Happy birthday! Here's your morning status..."

        unacked = check_response_acknowledges_events(response, events)
        self.assertEqual(len(unacked), 0)

    def test_birthday_not_acknowledged(self):
        """LLM says generic greeting → event NOT acknowledged."""
        from apps.life.services.event_acknowledgment import (
            check_response_acknowledges_events,
        )

        events = [{
            "type": "birthday",
            "priority": "self",
            "person": "Danny",
            "message": "Happy birthday, Danny!",
            "keywords": {"birthday", "born", "turning", "danny"},
        }]
        response = "Good morning! Here's your daily status."

        unacked = check_response_acknowledges_events(response, events)
        self.assertEqual(len(unacked), 1)

    def test_partial_response_not_sufficient(self):
        """'Great day' without birthday keyword → NOT acknowledged."""
        from apps.life.services.event_acknowledgment import (
            check_response_acknowledges_events,
        )

        events = [{
            "type": "birthday",
            "priority": "self",
            "person": "Danny",
            "message": "Happy birthday, Danny!",
            "keywords": {"birthday", "born", "turning", "danny"},
        }]
        response = "Hope you're having a great day today!"

        unacked = check_response_acknowledges_events(response, events)
        self.assertEqual(len(unacked), 1)

    def test_family_event_needs_person_name(self):
        """For non-self events, keyword + person name required."""
        from apps.life.services.event_acknowledgment import (
            check_response_acknowledges_events,
        )

        events = [{
            "type": "birthday",
            "priority": "family",
            "person": "Mom",
            "message": "Today is Mom's birthday.",
            "keywords": {"birthday", "born", "turning", "mom"},
        }]
        # Has 'birthday' but not 'Mom' → not acknowledged
        response = "Happy birthday vibes today! Here's your status."
        unacked = check_response_acknowledges_events(response, events)
        self.assertEqual(len(unacked), 1)

        # Has both → acknowledged
        response = "Today is Mom's birthday! Here's your status."
        unacked = check_response_acknowledges_events(response, events)
        self.assertEqual(len(unacked), 0)

    def test_multiple_events_partial_acknowledgment(self):
        """LLM acknowledges one event but misses another."""
        from apps.life.services.event_acknowledgment import (
            check_response_acknowledges_events,
        )

        events = [
            {
                "type": "birthday",
                "priority": "family",
                "person": "Mom",
                "message": "Today is Mom's birthday.",
                "keywords": {"birthday", "mom"},
            },
            {
                "type": "anniversary",
                "priority": "self",
                "person": "",
                "message": "Today is your 10th anniversary.",
                "keywords": {"anniversary"},
            },
        ]
        # Mentions Mom's birthday but not anniversary
        response = "Today is Mom's birthday! Here's your status."
        unacked = check_response_acknowledges_events(response, events)
        self.assertEqual(len(unacked), 1)
        self.assertEqual(unacked[0]["type"], "anniversary")

    def test_empty_response_all_unacknowledged(self):
        from apps.life.services.event_acknowledgment import (
            check_response_acknowledges_events,
        )

        events = [{
            "type": "birthday",
            "priority": "self",
            "person": "Danny",
            "message": "Happy birthday!",
            "keywords": {"birthday", "danny"},
        }]
        unacked = check_response_acknowledges_events("", events)
        self.assertEqual(len(unacked), 1)


# ═══════════════════════════════════════════════════════════════════
# Injection integration
# ═══════════════════════════════════════════════════════════════════


class TestInjectionIntegration(TestCase):
    """Test the full injection flow through PersonalAssistant."""

    def setUp(self):
        self.user = _create_test_user(email="inject_test@example.com")

    def test_injection_when_llm_missed(self):
        """LLM doesn't mention event → injection occurs."""
        from apps.life.models import SignificantEvent
        from apps.ai.personal_assistant import PersonalAssistant

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="Mom's Birthday",
            event_type="birthday",
            event_date=today,
            person_name="Mom",
        )

        pa = PersonalAssistant(self.user)
        llm_response = "Good morning! Here's your daily status."
        result = pa._inject_critical_signals(llm_response)

        self.assertIn("Mom", result)
        self.assertIn("birthday", result.lower())
        # Acknowledgment should be before LLM response
        self.assertTrue(result.index("Mom") < result.index("Good morning"))

    def test_no_injection_when_llm_acknowledged(self):
        """LLM mentions event → no injection."""
        from apps.life.models import SignificantEvent
        from apps.ai.personal_assistant import PersonalAssistant

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="Mom's Birthday",
            event_type="birthday",
            event_date=today,
            person_name="Mom",
        )

        pa = PersonalAssistant(self.user)
        llm_response = "Today is Mom's birthday! Here's your morning status..."
        result = pa._inject_critical_signals(llm_response)

        # Should NOT double up
        self.assertEqual(result.count("Mom"), llm_response.count("Mom"))

    def test_no_events_no_change(self):
        """No events → response returned unchanged."""
        from apps.ai.personal_assistant import PersonalAssistant

        pa = PersonalAssistant(self.user)
        llm_response = "Good morning! Here's your daily status."
        result = pa._inject_critical_signals(llm_response)

        self.assertEqual(result, llm_response)

    def test_backward_compatible_alias(self):
        """_inject_event_acknowledgment still works as alias."""
        from apps.ai.personal_assistant import PersonalAssistant

        # Class-level attribute should point to the same function
        self.assertIs(
            PersonalAssistant._inject_event_acknowledgment,
            PersonalAssistant._inject_critical_signals,
        )


# ═══════════════════════════════════════════════════════════════════
# Utility tests
# ═══════════════════════════════════════════════════════════════════


class TestOrdinal(TestCase):
    """Test ordinal suffix generation."""

    def test_ordinal_suffix(self):
        from apps.life.services.event_acknowledgment import _ordinal

        self.assertEqual(_ordinal(1), "1st")
        self.assertEqual(_ordinal(2), "2nd")
        self.assertEqual(_ordinal(3), "3rd")
        self.assertEqual(_ordinal(4), "4th")
        self.assertEqual(_ordinal(11), "11th")
        self.assertEqual(_ordinal(12), "12th")
        self.assertEqual(_ordinal(13), "13th")
        self.assertEqual(_ordinal(21), "21st")
        self.assertEqual(_ordinal(22), "22nd")
        self.assertEqual(_ordinal(23), "23rd")
        self.assertEqual(_ordinal(100), "100th")
        self.assertEqual(_ordinal(101), "101st")
        self.assertEqual(_ordinal(111), "111th")
