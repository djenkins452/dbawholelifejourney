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

        # Per CoS Strict Mode Isolation contract (2026-04-26):
        # the locked-facts block sent to the LLM contains ONLY the
        # NEXT ACTION line. Significant events are tracked in
        # build_locked_facts() output (and consumed by the truth
        # validator and other surfaces) but no longer leak into the
        # LLM prompt block — preventing mode blending.
        self.assertNotIn("Significant Events:", block)
        self.assertNotIn("SIGNIFICANT EVENT ACKNOWLEDGMENT", block)
        # The block still wraps the next action.
        self.assertIn("CURRENT NEXT ACTION", block)
        self.assertIn("test", block)  # next_action='test' from fixture
        # Confirm summary is still computed for non-LLM consumers.
        self.assertIn("TODAY:", summary)

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


class StrictModeIsolationLockedFactsTests(TestCase):
    """The locked-facts block sent to the LLM contains ONLY the next
    action line — no domain summaries, no overdue lists, no future
    items, no event acknowledgment. (Per CoS Strict Mode Isolation
    contract.) The richer build_locked_facts() dict is still
    available to the truth validator and other surfaces — only the
    LLM-facing prompt block is slimmed."""

    def test_block_contains_only_next_action_line(self):
        from apps.ai.cos_fact_statements import format_locked_facts_block
        facts = {
            'faith_summary': 'Bible reading is not yet completed.',
            'routine_summary': 'Morning Routine: 1/3 done.',
            'task_summary': 'Tasks: 2 pending.',
            'workout_summary': 'No workout scheduled today.',
            'journal_summary': 'Journal not written.',
            'medication_summary': 'Morning meds: pending.',
            'significant_events_summary': 'TODAY: Birthday — Mom.',
            'overall_summary': '1 of 8 done — keep going.',
            'next_action': 'Next: Bible reading. Do this now.',
        }
        block = format_locked_facts_block(facts)

        # The next action MUST appear.
        self.assertIn('Next: Bible reading. Do this now.', block)
        self.assertIn('CURRENT NEXT ACTION', block)

        # NONE of the domain summaries may appear — the LLM has no
        # material to blend.
        self.assertNotIn('Bible reading is not yet completed.', block)
        self.assertNotIn('Morning Routine:', block)
        self.assertNotIn('Tasks:', block)
        self.assertNotIn('No workout scheduled', block)
        self.assertNotIn('Journal not written', block)
        self.assertNotIn('Morning meds:', block)
        self.assertNotIn('Significant Events:', block)
        self.assertNotIn('Overall:', block)
        self.assertNotIn('SIGNIFICANT EVENT ACKNOWLEDGMENT', block)

    def test_block_falls_back_when_no_next_action(self):
        from apps.ai.cos_fact_statements import format_locked_facts_block
        facts = {'next_action': None}
        block = format_locked_facts_block(facts)
        self.assertIn('Nothing pending right now.', block)
