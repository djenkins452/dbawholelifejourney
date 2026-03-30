"""
Tests for deterministic critical signal acknowledgment.

Verifies:
1. Structured critical event objects with signal_type_rank
2. Acknowledgment builder generates correct text for each event type
3. Grouped multi-event phrasing (1, 2, 3+ events)
4. Structured idempotency: keyword + person name matching
5. Partial acknowledgment: only inject missed events
6. Edge language: "great day" != birthday acknowledgment
7. Priority ordering: self > spouse > family > general
8. Injection integration: prepend at top, no duplication
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
        self.assertEqual(get_today_critical_events(self.user), [])

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
        self.assertIn("signal_type_rank", ev)
        self.assertEqual(ev["signal_type_rank"], 10)
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
        SignificantEvent.objects.create(
            user=self.user, title="Mom's Birthday",
            event_type="birthday", event_date=today, person_name="Mom",
        )
        SignificantEvent.objects.create(
            user=self.user, title="My Birthday",
            event_type="birthday", event_date=today, person_name="Danny",
        )

        events = get_today_critical_events(self.user)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["priority"], "self")
        self.assertEqual(events[1]["priority"], "family")

    def test_future_event_not_included(self):
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            get_today_critical_events,
        )

        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        SignificantEvent.objects.create(
            user=self.user, title="Future Event",
            event_type="birthday", event_date=tomorrow, person_name="Someone",
        )
        self.assertEqual(get_today_critical_events(self.user), [])


# ═══════════════════════════════════════════════════════════════════
# Single-event acknowledgment text
# ═══════════════════════════════════════════════════════════════════


class TestBuildEventAcknowledgment(TestCase):
    """Test the text acknowledgment builder."""

    def setUp(self):
        self.user = _create_test_user(email="build_ack@example.com")

    def test_no_events_returns_none(self):
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )
        self.assertIsNone(build_event_acknowledgment(self.user))

    def test_self_birthday(self):
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )
        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user, title="My Birthday", event_type="birthday",
            event_date=today, person_name="Danny", original_year=1981,
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
            user=self.user, title="Mom's Birthday", event_type="birthday",
            event_date=today, person_name="Mom", original_year=1960,
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
            user=self.user, title="Wedding Anniversary",
            event_type="anniversary", event_date=today,
            person_name="", original_year=2016,
        )
        result = build_event_acknowledgment(self.user)
        self.assertIn("anniversary", result.lower())

    def test_memorial(self):
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )
        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user, title="Dad's Memorial", event_type="memorial",
            event_date=today, person_name="Dad",
        )
        result = build_event_acknowledgment(self.user)
        self.assertIn("Remembering", result)
        self.assertIn("Dad", result)


# ═══════════════════════════════════════════════════════════════════
# Grouped multi-event acknowledgment
# ═══════════════════════════════════════════════════════════════════


class TestGroupedAcknowledgment(TestCase):
    """Test natural grouping of multiple events."""

    def test_single_event_as_is(self):
        from apps.life.services.event_acknowledgment import (
            build_grouped_acknowledgment,
        )
        events = [{"message": "Happy birthday, Danny!", "type": "birthday"}]
        result = build_grouped_acknowledgment(events)
        self.assertEqual(result, "Happy birthday, Danny!")

    def test_two_events_joined_naturally(self):
        from apps.life.services.event_acknowledgment import (
            build_grouped_acknowledgment,
        )
        events = [
            {"message": "Happy birthday, Danny!", "type": "birthday"},
            {"message": "Today is Mom's birthday.", "type": "birthday"},
        ]
        result = build_grouped_acknowledgment(events)
        self.assertIn("Danny", result)
        self.assertIn("Mom", result)
        self.assertIn(" — and ", result)
        # Should be a single line (no newline for 2 events)
        self.assertNotIn("\n", result)

    def test_three_events_lead_plus_also(self):
        from apps.life.services.event_acknowledgment import (
            build_grouped_acknowledgment,
        )
        events = [
            {"message": "Happy birthday, Danny!", "type": "birthday"},
            {"message": "Today is Mom's birthday.", "type": "birthday"},
            {"message": "Today is your anniversary.", "type": "anniversary"},
        ]
        result = build_grouped_acknowledgment(events)
        self.assertIn("Danny", result)
        self.assertIn("Also today:", result)
        self.assertIn("Mom", result)
        self.assertIn("anniversary", result.lower())

    def test_empty_events_returns_none(self):
        from apps.life.services.event_acknowledgment import (
            build_grouped_acknowledgment,
        )
        self.assertIsNone(build_grouped_acknowledgment([]))

    def test_grouped_via_build_event_acknowledgment(self):
        """build_event_acknowledgment uses grouping for multiple events."""
        from apps.life.models import SignificantEvent
        from apps.life.services.event_acknowledgment import (
            build_event_acknowledgment,
        )
        user = _create_test_user(email="group_build@example.com")
        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=user, title="Mom's Birthday", event_type="birthday",
            event_date=today, person_name="Mom",
        )
        SignificantEvent.objects.create(
            user=user, title="Wedding Anniversary",
            event_type="anniversary", event_date=today, person_name="",
        )
        result = build_event_acknowledgment(user)
        self.assertIn("Mom", result)
        self.assertIn("anniversary", result.lower())
        # Should use natural grouping, not bare newline join
        self.assertIn(" — and ", result)


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
            "type": "birthday", "priority": "self", "person": "Danny",
            "message": "Happy birthday, Danny!",
            "keywords": {"birthday", "bday", "born", "turning", "danny"},
        }]
        unacked = check_response_acknowledges_events(
            "Happy birthday! Here's your morning status...", events,
        )
        self.assertEqual(len(unacked), 0)

    def test_bday_synonym_acknowledged(self):
        """LLM uses 'bday' synonym → still acknowledged."""
        from apps.life.services.event_acknowledgment import (
            check_response_acknowledges_events,
        )
        events = [{
            "type": "birthday", "priority": "self", "person": "Danny",
            "message": "Happy birthday, Danny!",
            "keywords": {"birthday", "bday", "born", "turning", "danny"},
        }]
        unacked = check_response_acknowledges_events(
            "Happy bday! Here's your status.", events,
        )
        self.assertEqual(len(unacked), 0)

    def test_birthday_not_acknowledged(self):
        """LLM says generic greeting → event NOT acknowledged."""
        from apps.life.services.event_acknowledgment import (
            check_response_acknowledges_events,
        )
        events = [{
            "type": "birthday", "priority": "self", "person": "Danny",
            "message": "Happy birthday, Danny!",
            "keywords": {"birthday", "bday", "born", "turning", "danny"},
        }]
        unacked = check_response_acknowledges_events(
            "Good morning! Here's your daily status.", events,
        )
        self.assertEqual(len(unacked), 1)

    def test_great_day_not_sufficient(self):
        """'Great day' without birthday keyword → NOT acknowledged."""
        from apps.life.services.event_acknowledgment import (
            check_response_acknowledges_events,
        )
        events = [{
            "type": "birthday", "priority": "self", "person": "Danny",
            "message": "Happy birthday, Danny!",
            "keywords": {"birthday", "bday", "born", "turning", "danny"},
        }]
        unacked = check_response_acknowledges_events(
            "Hope you're having a great day today!", events,
        )
        self.assertEqual(len(unacked), 1)

    def test_family_event_needs_person_name(self):
        """For non-self events, keyword + person name required."""
        from apps.life.services.event_acknowledgment import (
            check_response_acknowledges_events,
        )
        events = [{
            "type": "birthday", "priority": "family", "person": "Mom",
            "message": "Today is Mom's birthday.",
            "keywords": {"birthday", "bday", "born", "turning", "mom"},
        }]
        # Has keyword but not person → not acknowledged
        unacked = check_response_acknowledges_events(
            "Happy birthday vibes today!", events,
        )
        self.assertEqual(len(unacked), 1)

        # Has both → acknowledged
        unacked = check_response_acknowledges_events(
            "Today is Mom's birthday! Here's your status.", events,
        )
        self.assertEqual(len(unacked), 0)

    def test_partial_acknowledgment(self):
        """LLM acknowledges one event but misses another."""
        from apps.life.services.event_acknowledgment import (
            check_response_acknowledges_events,
        )
        events = [
            {
                "type": "birthday", "priority": "family", "person": "Mom",
                "message": "Today is Mom's birthday.",
                "keywords": {"birthday", "mom"},
            },
            {
                "type": "anniversary", "priority": "self", "person": "",
                "message": "Today is your 10th anniversary.",
                "keywords": {"anniversary"},
            },
        ]
        # Mentions Mom's birthday but not anniversary
        unacked = check_response_acknowledges_events(
            "Today is Mom's birthday! Here's your status.", events,
        )
        self.assertEqual(len(unacked), 1)
        self.assertEqual(unacked[0]["type"], "anniversary")

    def test_empty_response_all_unacknowledged(self):
        from apps.life.services.event_acknowledgment import (
            check_response_acknowledges_events,
        )
        events = [{
            "type": "birthday", "priority": "self", "person": "Danny",
            "message": "Happy birthday!", "keywords": {"birthday", "danny"},
        }]
        self.assertEqual(
            len(check_response_acknowledges_events("", events)), 1,
        )


# ═══════════════════════════════════════════════════════════════════
# Injection integration
# ═══════════════════════════════════════════════════════════════════


class TestInjectionIntegration(TestCase):
    """Test the full injection flow through PersonalAssistant."""

    def setUp(self):
        self.user = _create_test_user(email="inject_test@example.com")

    def test_injection_when_llm_missed(self):
        """LLM doesn't mention event → injection occurs at top."""
        from apps.life.models import SignificantEvent
        from apps.ai.personal_assistant import PersonalAssistant

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user, title="Mom's Birthday", event_type="birthday",
            event_date=today, person_name="Mom",
        )

        pa = PersonalAssistant(self.user)
        result = pa._inject_critical_signals(
            "Good morning! Here's your daily status.",
        )
        self.assertIn("Mom", result)
        self.assertIn("birthday", result.lower())
        # Must be at top
        self.assertTrue(result.index("Mom") < result.index("Good morning"))

    def test_no_injection_when_llm_acknowledged(self):
        """LLM mentions event → no injection."""
        from apps.life.models import SignificantEvent
        from apps.ai.personal_assistant import PersonalAssistant

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user, title="Mom's Birthday", event_type="birthday",
            event_date=today, person_name="Mom",
        )

        pa = PersonalAssistant(self.user)
        llm_response = "Today is Mom's birthday! Here's your morning status..."
        result = pa._inject_critical_signals(llm_response)
        self.assertEqual(result.count("Mom"), llm_response.count("Mom"))

    def test_partial_injection_only_missed(self):
        """LLM handles one event, misses another → only missed injected."""
        from apps.life.models import SignificantEvent
        from apps.ai.personal_assistant import PersonalAssistant

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user, title="Mom's Birthday", event_type="birthday",
            event_date=today, person_name="Mom",
        )
        SignificantEvent.objects.create(
            user=self.user, title="Wedding Anniversary",
            event_type="anniversary", event_date=today,
            person_name="", original_year=2016,
        )

        pa = PersonalAssistant(self.user)
        # LLM acknowledges Mom but not anniversary
        llm_response = "Today is Mom's birthday! Here's your status."
        result = pa._inject_critical_signals(llm_response)

        # Anniversary should be injected, Mom should NOT be duplicated
        self.assertIn("anniversary", result.lower())
        self.assertEqual(result.count("Mom"), 1)

    def test_no_events_no_change(self):
        from apps.ai.personal_assistant import PersonalAssistant
        pa = PersonalAssistant(self.user)
        llm_response = "Good morning!"
        self.assertEqual(pa._inject_critical_signals(llm_response), llm_response)

    def test_backward_compatible_alias(self):
        from apps.ai.personal_assistant import PersonalAssistant
        self.assertIs(
            PersonalAssistant._inject_event_acknowledgment,
            PersonalAssistant._inject_critical_signals,
        )


# ═══════════════════════════════════════════════════════════════════
# Utility tests
# ═══════════════════════════════════════════════════════════════════


class TestOrdinal(TestCase):
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
        self.assertEqual(_ordinal(101), "101st")
        self.assertEqual(_ordinal(111), "111th")
