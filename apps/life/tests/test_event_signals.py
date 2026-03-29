"""
Tests for Significant Event Signal Builder.

Verifies deterministic signal generation from event state data.
Pure function tests — no DB required for signal builder itself.
"""
from django.test import TestCase

from apps.life.services.event_signals import (
    build_significant_event_signals,
    infer_relationship_priority,
    PRIORITY_SELF,
    PRIORITY_SPOUSE,
    PRIORITY_CHILD,
    PRIORITY_FAMILY,
    PRIORITY_GENERAL,
)


class TestInferRelationshipPriority(TestCase):
    """Test deterministic relationship priority inference."""

    def test_self_from_person_name(self):
        """User's own birthday detected from person_name."""
        ev = {"title": "My Birthday", "person": "Danny", "type": "birthday"}
        self.assertEqual(infer_relationship_priority(ev), PRIORITY_SELF)

    def test_self_from_keyword(self):
        ev = {"title": "Birthday", "person": "me", "type": "birthday"}
        self.assertEqual(infer_relationship_priority(ev), PRIORITY_SELF)

    def test_spouse_from_relationship_type(self):
        """Structured relationship_type takes precedence."""
        ev = {
            "title": "Wife's Birthday",
            "person": "Sarah",
            "type": "birthday",
            "relationship_type": "spouse",
        }
        self.assertEqual(infer_relationship_priority(ev), PRIORITY_SPOUSE)

    def test_spouse_from_keyword(self):
        ev = {"title": "Wife Birthday", "person": "Beth", "type": "birthday"}
        self.assertEqual(infer_relationship_priority(ev), PRIORITY_SPOUSE)

    def test_child_from_keyword(self):
        ev = {"title": "Son's Birthday", "person": "Jake", "type": "birthday"}
        self.assertEqual(infer_relationship_priority(ev), PRIORITY_CHILD)

    def test_family_from_person_type(self):
        """Person.person_type = 'family' maps to PRIORITY_FAMILY."""
        ev = {
            "title": "Birthday",
            "person": "Uncle Bob",
            "type": "birthday",
            "person_type": "family",
        }
        self.assertEqual(infer_relationship_priority(ev), PRIORITY_FAMILY)

    def test_family_from_keyword(self):
        ev = {"title": "Mom's Birthday", "person": "Mom", "type": "birthday"}
        self.assertEqual(infer_relationship_priority(ev), PRIORITY_FAMILY)

    def test_general_fallback(self):
        ev = {"title": "Office Party", "person": "Team", "type": "other"}
        self.assertEqual(infer_relationship_priority(ev), PRIORITY_GENERAL)

    def test_relationship_type_overrides_keyword(self):
        """Structured data takes precedence over keyword inference."""
        ev = {
            "title": "Birthday",
            "person": "Mom",
            "type": "birthday",
            "relationship_type": "spouse",
        }
        # relationship_type=spouse overrides "Mom" keyword
        self.assertEqual(infer_relationship_priority(ev), PRIORITY_SPOUSE)


class TestBuildSignificantEventSignals(TestCase):
    """Test signal generation from event state data."""

    def test_empty_state_returns_empty(self):
        self.assertEqual(build_significant_event_signals({}), [])
        self.assertEqual(build_significant_event_signals(None), [])

    def test_today_event_generates_mandatory_signal(self):
        """Today events produce mandatory signal."""
        state = {
            "today_events": [
                {"title": "My Birthday", "type": "birthday",
                 "days_until": 0, "person": "Danny", "years": 45},
            ],
            "approaching_events": [
                {"title": "My Birthday", "type": "birthday",
                 "days_until": 0, "person": "Danny", "years": 45},
            ],
        }
        signals = build_significant_event_signals(state)
        today_sig = next(
            (s for s in signals if s["key"] == "significant_event_today"),
            None,
        )
        self.assertIsNotNone(today_sig)
        self.assertTrue(today_sig["mandatory"])
        self.assertEqual(today_sig["priority"], PRIORITY_SELF)
        self.assertEqual(today_sig["priority_label"], "self")
        self.assertIn("Birthday", today_sig["insight"])

    def test_upcoming_event_generates_signal(self):
        """Upcoming events produce approaching signal."""
        state = {
            "today_events": [],
            "approaching_events": [
                {"title": "Wife's Birthday", "type": "birthday",
                 "days_until": 7, "person": "Beth"},
            ],
        }
        signals = build_significant_event_signals(state)
        upcoming = next(
            (s for s in signals if s["key"] == "significant_event_upcoming"),
            None,
        )
        self.assertIsNotNone(upcoming)
        self.assertEqual(upcoming["state"], "approaching")
        self.assertEqual(upcoming["priority"], PRIORITY_SPOUSE)

    def test_gift_window_for_family_birthday(self):
        """Gift consideration signal for spouse/family birthdays."""
        state = {
            "today_events": [],
            "approaching_events": [
                {"title": "Wife's Birthday", "type": "birthday",
                 "days_until": 10, "person": "Beth"},
            ],
        }
        signals = build_significant_event_signals(state)
        gift_sig = next(
            (s for s in signals if s["key"] == "gift_consideration_window"),
            None,
        )
        self.assertIsNotNone(gift_sig)
        self.assertIn("gift planning", gift_sig["insight"])

    def test_no_gift_window_for_non_birthday(self):
        """Gift signal only for birthdays."""
        state = {
            "today_events": [],
            "approaching_events": [
                {"title": "Wedding Anniversary", "type": "anniversary",
                 "days_until": 10, "person": "Beth"},
            ],
        }
        signals = build_significant_event_signals(state)
        gift_sig = next(
            (s for s in signals if s["key"] == "gift_consideration_window"),
            None,
        )
        self.assertIsNone(gift_sig)

    def test_no_gift_window_for_general_person(self):
        """Gift signal only for family or closer."""
        state = {
            "today_events": [],
            "approaching_events": [
                {"title": "Coworker Birthday", "type": "birthday",
                 "days_until": 10, "person": "Bob from work"},
            ],
        }
        signals = build_significant_event_signals(state)
        gift_sig = next(
            (s for s in signals if s["key"] == "gift_consideration_window"),
            None,
        )
        self.assertIsNone(gift_sig)

    def test_no_events_returns_empty(self):
        """No events = no signals."""
        state = {"today_events": [], "approaching_events": []}
        self.assertEqual(build_significant_event_signals(state), [])

    def test_multiple_today_events(self):
        """Multiple today events produce single signal with highest priority."""
        state = {
            "today_events": [
                {"title": "My Birthday", "type": "birthday",
                 "days_until": 0, "person": "Danny"},
                {"title": "Mom's Birthday", "type": "birthday",
                 "days_until": 0, "person": "Mom"},
            ],
            "approaching_events": [
                {"title": "My Birthday", "type": "birthday",
                 "days_until": 0, "person": "Danny"},
                {"title": "Mom's Birthday", "type": "birthday",
                 "days_until": 0, "person": "Mom"},
            ],
        }
        signals = build_significant_event_signals(state)
        today_sig = next(
            (s for s in signals if s["key"] == "significant_event_today"),
            None,
        )
        self.assertIsNotNone(today_sig)
        # Self priority wins over family
        self.assertEqual(today_sig["priority"], PRIORITY_SELF)
        # Both events in the signal
        self.assertEqual(len(today_sig["events"]), 2)
