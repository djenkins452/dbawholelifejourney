"""
Tests for significant event integration into LOCKED FACTS.

Verifies that today's events appear in the locked facts block
with mandatory acknowledgment rules.
"""
import datetime

from django.conf import settings
from django.test import TestCase

from apps.users.models import User, TermsAcceptance


def _create_test_user():
    """Create a test user with required onboarding."""
    user = User.objects.create_user(
        email="event_test@example.com", password="testpass123",
    )
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class TestSignificantEventLockedFacts(TestCase):
    """Test that significant events are surfaced in locked facts."""

    def setUp(self):
        self.user = _create_test_user()

    def test_no_events_summary(self):
        """No events produces neutral summary."""
        from apps.ai.cos_fact_statements import _build_significant_event_summary
        summary, signals = _build_significant_event_summary(self.user)
        self.assertEqual(summary, "No significant events today or upcoming.")
        self.assertEqual(signals, [])

    def test_today_birthday_in_summary(self):
        """User's own birthday today appears as mandatory locked fact."""
        from apps.life.models import SignificantEvent
        from apps.ai.cos_fact_statements import _build_significant_event_summary

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="My Birthday",
            event_type="birthday",
            event_date=today,
            person_name="Danny",
            original_year=1981,
        )

        summary, signals = _build_significant_event_summary(self.user)
        self.assertIn("TODAY IS YOUR BIRTHDAY", summary)
        self.assertTrue(len(signals) > 0)
        today_sig = next(
            (s for s in signals if s["key"] == "significant_event_today"),
            None,
        )
        self.assertIsNotNone(today_sig)
        self.assertTrue(today_sig["mandatory"])

    def test_today_event_in_locked_facts_block(self):
        """Today events appear in the formatted locked facts block."""
        from apps.life.models import SignificantEvent
        from apps.ai.cos_fact_statements import (
            _build_significant_event_summary,
            format_locked_facts_block,
        )

        today = datetime.date.today()
        SignificantEvent.objects.create(
            user=self.user,
            title="Mom's Birthday",
            event_type="birthday",
            event_date=today,
            person_name="Mom",
        )

        summary, signals = _build_significant_event_summary(self.user)
        self.assertIn("TODAY:", summary)

        # Build a minimal facts dict to test formatting
        facts = {
            'faith_summary': 'test',
            'routine_summary': 'test',
            'task_summary': 'test',
            'workout_summary': 'test',
            'journal_summary': 'test',
            'medication_summary': 'test',
            'significant_events_summary': summary,
            'overall_summary': 'test',
            'next_action': 'test',
        }
        block = format_locked_facts_block(facts)

        self.assertIn("Significant Events:", block)
        self.assertIn("TODAY:", block)
        self.assertIn("SIGNIFICANT EVENT ACKNOWLEDGMENT (MANDATORY)", block)
        self.assertIn("NON-NEGOTIABLE", block)

    def test_no_today_event_no_mandatory_rules(self):
        """Without today events, no mandatory acknowledgment rules."""
        from apps.ai.cos_fact_statements import format_locked_facts_block

        facts = {
            'faith_summary': 'test',
            'routine_summary': 'test',
            'task_summary': 'test',
            'workout_summary': 'test',
            'journal_summary': 'test',
            'medication_summary': 'test',
            'significant_events_summary': 'No significant events today or upcoming.',
            'overall_summary': 'test',
            'next_action': 'test',
        }
        block = format_locked_facts_block(facts)
        self.assertNotIn("SIGNIFICANT EVENT ACKNOWLEDGMENT", block)

    def test_upcoming_family_event_in_summary(self):
        """Upcoming family events appear in summary."""
        from apps.life.models import SignificantEvent
        from apps.ai.cos_fact_statements import _build_significant_event_summary

        today = datetime.date.today()
        future = today + datetime.timedelta(days=5)
        SignificantEvent.objects.create(
            user=self.user,
            title="Mom's Birthday",
            event_type="birthday",
            event_date=future,
            person_name="Mom",
        )

        summary, signals = _build_significant_event_summary(self.user)
        self.assertIn("Upcoming:", summary)
        self.assertIn("Mom", summary)
