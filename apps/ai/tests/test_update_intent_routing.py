# ==============================================================================
# File: tests/test_update_intent_routing.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for calendar update intent routing — ensures mutation verbs
#              route to mutate_calendar_event, not read_calendar_events.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-24
# ==============================================================================
"""
Update Intent Routing Tests

Validates that:
1. "change" verb → mutate_calendar_event(action="update")
2. "move" verb → mutate_calendar_event(action="update")
3. "from X to Y" phrase → mutate_calendar_event(action="update")
4. weekday modifier preserved → event_date passed correctly
5. event_query resolves to correct event_id
6. Mutation verb enforcement reroutes misclassified read_calendar_events
"""

import datetime as dt
from unittest.mock import patch, MagicMock
from uuid import uuid4

import pytz
from django.test import TestCase

from apps.calendar_engine.models import CalendarEvent
from apps.calendar_engine.utils.idempotency import compute_idempotency_key
from apps.users.models import User


class _IntentUserMixin:
    """Setup helper."""

    def _create_user(self, email='intenttest@example.com'):
        from django.conf import settings as django_settings
        from apps.users.models import TermsAcceptance

        user = User.objects.create_user(
            email=email,
            password='testpass123',
            first_name='Intent',
        )
        prefs = user.preferences
        prefs.timezone = 'America/New_York'
        prefs.has_completed_onboarding = True
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.save()

        terms_version = django_settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        TermsAcceptance.objects.create(
            user=user,
            terms_version=terms_version,
        )
        return user

    def _create_event(self, user, title, start_dt, end_dt=None, **kwargs):
        """Helper: create a CalendarEvent with proper idempotency key."""
        if end_dt is None:
            end_dt = start_dt + dt.timedelta(hours=1)
        idem_key = compute_idempotency_key(user.id, title, start_dt, end_dt=end_dt)
        return CalendarEvent.objects.create(
            user=user,
            title=title,
            start_dt=start_dt,
            end_dt=end_dt,
            idempotency_key=idem_key,
            status=CalendarEvent.STATUS_SCHEDULED,
            **kwargs,
        )


# ──────────────────────────────────────────────────────────
# 1) Mutation verb enforcement in IntentService
# ──────────────────────────────────────────────────────────

class TestMutationVerbEnforcement(_IntentUserMixin, TestCase):
    """
    When the LLM misclassifies a mutation request as read_calendar_events,
    the _enforce_mutation_routing method must reroute it.
    """

    def setUp(self):
        self.user = self._create_user()
        from apps.ai.intent_service import IntentService
        self.service = IntentService.__new__(IntentService)

    def test_change_verb_triggers_reroute(self):
        """'change' in message → reroute to mutate_calendar_event."""
        read_params = {
            'query_text': 'Workout',
            'date_range_start': 'next wednesday',
            'timezone': 'America/New_York',
        }
        result = self.service._enforce_mutation_routing(
            "Change my Workout next Wednesday from 6:15am to 7:00am",
            read_params,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['intent_type'], 'mutate_calendar_event')
        self.assertEqual(result['parameters']['action'], 'update')
        self.assertEqual(result['parameters']['event_query'], 'Workout')
        self.assertEqual(result['parameters']['event_date'], 'next wednesday')

    def test_move_verb_triggers_reroute(self):
        """'move' in message → reroute to mutate_calendar_event."""
        read_params = {
            'query_text': 'meeting',
            'date_range_start': 'wednesday',
            'timezone': 'America/New_York',
        }
        result = self.service._enforce_mutation_routing(
            "Move my meeting on Wednesday to Thursday",
            read_params,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['intent_type'], 'mutate_calendar_event')
        self.assertEqual(result['parameters']['action'], 'update')

    def test_reschedule_verb_triggers_reroute(self):
        """'reschedule' in message → reroute to mutate_calendar_event."""
        result = self.service._enforce_mutation_routing(
            "Reschedule my dentist appointment to Friday",
            {'query_text': 'dentist', 'timezone': 'America/New_York'},
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['parameters']['action'], 'update')

    def test_cancel_verb_triggers_delete(self):
        """'cancel' in message → reroute with action='delete'."""
        result = self.service._enforce_mutation_routing(
            "Cancel my Wednesday event",
            {'query_text': 'event', 'date_range_start': 'wednesday',
             'timezone': 'America/New_York'},
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['parameters']['action'], 'delete')

    def test_from_to_phrase_triggers_reroute(self):
        """'from X to Y' pattern → reroute to mutate_calendar_event."""
        result = self.service._enforce_mutation_routing(
            "I need my appointment from 2pm to 3pm",
            {'query_text': 'appointment', 'timezone': 'America/New_York'},
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['parameters']['action'], 'update')

    def test_pure_read_not_rerouted(self):
        """'what's on my calendar' → no reroute (pure read)."""
        result = self.service._enforce_mutation_routing(
            "What's on my calendar tomorrow?",
            {'date_range_start': 'tomorrow', 'timezone': 'America/New_York'},
        )
        self.assertIsNone(result)

    def test_show_events_not_rerouted(self):
        """'show me my meetings' → no reroute (pure read)."""
        result = self.service._enforce_mutation_routing(
            "Show me my meetings this week",
            {'query_text': 'meetings', 'timezone': 'America/New_York'},
        )
        self.assertIsNone(result)


# ──────────────────────────────────────────────────────────
# 2) event_query resolution in handler
# ──────────────────────────────────────────────────────────

class TestEventQueryResolution(_IntentUserMixin, TestCase):
    """
    When mutate_calendar_event receives event_query instead of event_id,
    the handler must resolve it to the correct event.
    """

    def setUp(self):
        self.user = self._create_user('eqresolution@example.com')
        from apps.ai.action_handlers import ActionHandler
        self.handler = ActionHandler(self.user)
        self.tz = pytz.timezone('America/New_York')

    def test_update_with_event_query_finds_event(self):
        """Update via event_query resolves and updates the event."""
        start = self.tz.localize(dt.datetime(2026, 2, 26, 6, 15))
        ev = self._create_event(self.user, 'Workout', start)

        result = self.handler.handle_mutate_calendar_event(
            action='update',
            idempotency_key='test-eq-update',
            timezone='America/New_York',
            event_query='Workout',
            event_date='2026-02-26',
            start_time='07:00',
        )

        self.assertTrue(result.success, f"Expected success but got: {result.message}")
        ev.refresh_from_db()
        local = ev.start_dt.astimezone(self.tz)
        self.assertEqual(local.hour, 7)
        self.assertEqual(local.minute, 0)

    def test_update_with_event_query_no_match(self):
        """Update with non-matching event_query returns error."""
        result = self.handler.handle_mutate_calendar_event(
            action='update',
            idempotency_key='test-eq-nomatch',
            timezone='America/New_York',
            event_query='Nonexistent Event',
            event_date='2026-02-26',
            start_time='07:00',
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, 'event_not_found')

    def test_delete_with_event_query(self):
        """Delete via event_query resolves and soft-deletes."""
        start = self.tz.localize(dt.datetime(2026, 2, 26, 10, 0))
        ev = self._create_event(self.user, 'Team Meeting', start)

        result = self.handler.handle_mutate_calendar_event(
            action='delete',
            idempotency_key='test-eq-delete',
            timezone='America/New_York',
            event_query='Team Meeting',
            event_date='2026-02-26',
        )

        self.assertTrue(result.success)
        ev.refresh_from_db()
        self.assertEqual(ev.status, CalendarEvent.STATUS_CANCELED)

    def test_event_query_picks_nearest_upcoming(self):
        """When multiple events match, picks the nearest upcoming one."""
        start_past = self.tz.localize(dt.datetime(2026, 2, 20, 6, 15))
        start_future = self.tz.localize(dt.datetime(2026, 3, 5, 6, 15))

        ev_past = self._create_event(self.user, 'Workout', start_past)
        ev_future = self._create_event(self.user, 'Workout', start_future)

        result = self.handler.handle_mutate_calendar_event(
            action='update',
            idempotency_key='test-eq-nearest',
            timezone='America/New_York',
            event_query='Workout',
            start_time='07:00',
        )

        self.assertTrue(result.success)
        # Should have updated the future event, not the past one
        ev_future.refresh_from_db()
        local = ev_future.start_dt.astimezone(self.tz)
        self.assertEqual(local.hour, 7)

    def test_event_query_case_insensitive(self):
        """event_query matching is case-insensitive."""
        start = self.tz.localize(dt.datetime(2026, 2, 26, 6, 15))
        ev = self._create_event(self.user, 'Bible Study', start)

        result = self.handler.handle_mutate_calendar_event(
            action='update',
            idempotency_key='test-eq-case',
            timezone='America/New_York',
            event_query='bible study',
            event_date='2026-02-26',
            start_time='18:00',
        )

        self.assertTrue(result.success)
        ev.refresh_from_db()
        local = ev.start_dt.astimezone(self.tz)
        self.assertEqual(local.hour, 18)


# ──────────────────────────────────────────────────────────
# 3) Tool schema validation: mutation verbs → correct tool
# ──────────────────────────────────────────────────────────

class TestToolSchemaClarity(_IntentUserMixin, TestCase):
    """
    Verify the tool schema descriptions enforce correct routing.
    These are structural tests — they inspect the schema definitions.
    """

    def test_mutate_schema_mentions_mutation_verbs(self):
        """mutate_calendar_event description must mention move/change/reschedule."""
        from apps.ai.intents.calendar_intents import CALENDAR_INTENT_TOOLS

        mutate_tool = None
        for tool in CALENDAR_INTENT_TOOLS:
            if tool['function']['name'] == 'mutate_calendar_event':
                mutate_tool = tool
                break

        self.assertIsNotNone(mutate_tool)
        desc = mutate_tool['function']['description']

        for verb in ['move', 'change', 'reschedule', 'shift', 'update']:
            self.assertIn(verb, desc.lower(),
                          f"mutate_calendar_event description should mention '{verb}'")

    def test_mutate_schema_has_event_query_param(self):
        """mutate_calendar_event must have event_query parameter."""
        from apps.ai.intents.calendar_intents import CALENDAR_INTENT_TOOLS

        mutate_tool = None
        for tool in CALENDAR_INTENT_TOOLS:
            if tool['function']['name'] == 'mutate_calendar_event':
                mutate_tool = tool
                break

        props = mutate_tool['function']['parameters']['properties']
        self.assertIn('event_query', props,
                       "mutate_calendar_event must have event_query parameter")
        self.assertIn('event_date', props,
                       "mutate_calendar_event must have event_date parameter")

    def test_read_schema_excludes_mutation_verbs(self):
        """read_calendar_events description should say NOT to use for mutations."""
        from apps.ai.intents.calendar_intents import CALENDAR_INTENT_TOOLS

        read_tool = None
        for tool in CALENDAR_INTENT_TOOLS:
            if tool['function']['name'] == 'read_calendar_events':
                read_tool = tool
                break

        self.assertIsNotNone(read_tool)
        desc = read_tool['function']['description'].lower()
        self.assertIn('not', desc,
                       "read_calendar_events should warn against mutation use")

    def test_action_enum_has_update(self):
        """action parameter must include 'update' in enum."""
        from apps.ai.intents.calendar_intents import CALENDAR_INTENT_TOOLS

        mutate_tool = None
        for tool in CALENDAR_INTENT_TOOLS:
            if tool['function']['name'] == 'mutate_calendar_event':
                mutate_tool = tool
                break

        action_prop = mutate_tool['function']['parameters']['properties']['action']
        self.assertIn('update', action_prop['enum'])
        # The action description should mention mutation verbs
        self.assertIn('move', action_prop['description'].lower())
