"""
Tests for Calendar Reliability Hardening.

Covers:
- Part 1: Authoritative local date/time — "tomorrow" resolves correctly
- Part 2: Strict parameter inheritance — "same" clones inherit time
- Part 3: Safety invariants — no silent time defaults during clone
- Part 4: Debug logging — structured logs at decision points

These tests enforce scheduling determinism, timezone-correctness,
and parameter-consistency as reliability invariants.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytz
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.users.models import User


class AuthoritativeLocalDateTimeTests(TestCase):
    """Part 1: get_current_local_datetime() and intent service date authority."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='tz-test@example.com',
            password='testpass123',
            first_name='TZ',
        )
        prefs = self.user.preferences
        prefs.timezone = 'America/New_York'
        prefs.save()

    def test_get_current_local_datetime_alias_exists(self):
        """get_current_local_datetime is a callable alias for get_user_now."""
        from apps.core.utils import get_current_local_datetime, get_user_now
        self.assertIs(get_current_local_datetime, get_user_now)

    def test_get_current_local_datetime_returns_user_timezone(self):
        """Returned datetime uses user's configured timezone, not UTC."""
        from apps.core.utils import get_current_local_datetime
        result = get_current_local_datetime(self.user)
        self.assertIsNotNone(result.tzinfo)
        self.assertIn('America/New_York', str(result.tzinfo))

    @patch('apps.core.utils.timezone.now')
    def test_tomorrow_resolves_correctly_when_utc_date_differs(self, mock_now):
        """
        Guard test: If server UTC date differs from user local date,
        scheduling still uses the local date.

        Scenario: Feb 21, 10:24 PM Eastern = Feb 22, 3:24 AM UTC.
        "Tomorrow" should be Feb 22 (local), NOT Feb 23 (UTC+1).
        """
        # Mock UTC time: Feb 22, 2026 03:24 AM UTC
        # This corresponds to Feb 21, 2026 10:24 PM Eastern
        mock_utc = datetime(2026, 2, 22, 3, 24, 0, tzinfo=pytz.UTC)
        mock_now.return_value = mock_utc

        from apps.core.utils import get_current_local_datetime
        user_now = get_current_local_datetime(self.user)

        # User's local date should be Feb 21 (not Feb 22)
        self.assertEqual(user_now.date(), date(2026, 2, 21))

        # "Tomorrow" from user's perspective = Feb 22
        tomorrow = user_now.date() + timedelta(days=1)
        self.assertEqual(tomorrow, date(2026, 2, 22))

    @patch('apps.core.utils.timezone.now')
    def test_tomorrow_workout_at_615am(self, mock_now):
        """
        Full integration: "Log a 6:15am workout for tomorrow morning"
        when local time is Feb 21, 10:24 PM Eastern.

        Assert scheduled date == Feb 22 at 06:15 local time.
        """
        # Feb 22 3:24 AM UTC = Feb 21 10:24 PM Eastern
        mock_utc = datetime(2026, 2, 22, 3, 24, 0, tzinfo=pytz.UTC)
        mock_now.return_value = mock_utc

        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)

        result = handler.handle_create_event(
            title="Morning Workout",
            start_date="tomorrow",
            start_time="06:15",
            event_type="health",
        )

        self.assertTrue(result.success)

        # Verify the created event
        from apps.calendar_engine.models import CalendarEvent
        event = CalendarEvent.objects.get(id=result.created_object['id'])

        # Convert to user's timezone to check local date and time
        eastern = pytz.timezone('America/New_York')
        local_start = event.start_dt.astimezone(eastern)

        self.assertEqual(local_start.date(), date(2026, 2, 22))
        self.assertEqual(local_start.hour, 6)
        self.assertEqual(local_start.minute, 15)

    @patch('apps.core.utils.timezone.now')
    def test_intent_prompt_uses_user_local_date(self, mock_now):
        """
        The intent service system prompt must use user's local date,
        not server UTC, to provide correct 'today' context to OpenAI.
        """
        # Feb 22 3:24 AM UTC = Feb 21 10:24 PM Eastern
        mock_utc = datetime(2026, 2, 22, 3, 24, 0, tzinfo=pytz.UTC)
        mock_now.return_value = mock_utc

        from apps.ai.intent_service import IntentService
        service = IntentService.__new__(IntentService)

        prompt = service._build_intent_system_prompt(user=self.user)

        # The prompt should contain Feb 21 (local), NOT Feb 22 (UTC)
        self.assertIn('2026-02-21', prompt)
        self.assertNotIn('2026-02-22', prompt)

    def test_intent_prompt_warns_without_user(self):
        """When no user is passed, prompt falls back to UTC with warning."""
        from apps.ai.intent_service import IntentService
        service = IntentService.__new__(IntentService)

        with self.assertLogs('apps.ai.intent_service', level='WARNING') as cm:
            service._build_intent_system_prompt(user=None)

        self.assertTrue(any('no user supplied' in m for m in cm.output))


class ParameterInheritanceTests(TestCase):
    """Part 2: Strict parameter inheritance for 'same' / clone events."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='clone-test@example.com',
            password='testpass123',
            first_name='Clone',
        )
        prefs = self.user.preferences
        prefs.timezone = 'America/New_York'
        prefs.save()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_scheduling_context_stored_after_create_event(self):
        """After creating an event, scheduling context is stored in cache."""
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)

        handler.handle_create_event(
            title="Morning Workout",
            start_date="2026-02-22",
            start_time="06:15",
            event_type="health",
            location="YMCA",
        )

        ctx = ActionHandler._get_scheduling_context(self.user)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx['title'], "Morning Workout")
        self.assertEqual(ctx['start_time'], "06:15")
        self.assertEqual(ctx['event_type'], "health")
        self.assertEqual(ctx['location'], "YMCA")

    def test_clone_inherits_time_from_prior_event(self):
        """
        "Schedule the same workout on Feb 24" must inherit 06:15 AM
        from the prior event — no 9:00 AM default.
        """
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)

        # Step 1: Create original event at 06:15
        handler.handle_create_event(
            title="Morning Workout",
            start_date="2026-02-22",
            start_time="06:15",
            event_type="health",
        )

        # Step 2: Clone to Feb 24 — no start_time provided
        result = handler.handle_create_event(
            title="Morning Workout",
            start_date="2026-02-24",
            clone_from_last=True,
        )

        self.assertTrue(result.success)

        from apps.calendar_engine.models import CalendarEvent
        event = CalendarEvent.objects.get(id=result.created_object['id'])

        eastern = pytz.timezone('America/New_York')
        local_start = event.start_dt.astimezone(eastern)

        # Must be 06:15, NOT all-day or 09:00
        self.assertEqual(local_start.hour, 6)
        self.assertEqual(local_start.minute, 15)
        self.assertFalse(event.is_all_day)

    def test_clone_multiple_dates_all_inherit_time(self):
        """
        "Schedule the same workout on Feb 24, 25, 26, 27"
        All four events must be at 06:15 AM — no fallback default.
        """
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)

        # Original at 06:15
        handler.handle_create_event(
            title="Morning Workout",
            start_date="2026-02-22",
            start_time="06:15",
            event_type="health",
        )

        # Clone to four dates
        dates = ["2026-02-24", "2026-02-25", "2026-02-26", "2026-02-27"]
        results = []
        for d in dates:
            r = handler.handle_create_event(
                title="Morning Workout",
                start_date=d,
                clone_from_last=True,
            )
            self.assertTrue(r.success, f"Failed for {d}: {r.message}")
            results.append(r)

        # Verify all at 06:15
        from apps.calendar_engine.models import CalendarEvent
        eastern = pytz.timezone('America/New_York')

        for r in results:
            event = CalendarEvent.objects.get(id=r.created_object['id'])
            local_start = event.start_dt.astimezone(eastern)
            self.assertEqual(local_start.hour, 6,
                             f"Event {event.title} on {local_start.date()} "
                             f"has hour={local_start.hour}, expected 6")
            self.assertEqual(local_start.minute, 15)
            self.assertFalse(event.is_all_day)

    def test_clone_inherits_location(self):
        """Clone inherits location from prior event."""
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)

        handler.handle_create_event(
            title="Workout",
            start_date="2026-02-22",
            start_time="06:15",
            location="Planet Fitness",
        )

        result = handler.handle_create_event(
            title="Workout",
            start_date="2026-02-24",
            clone_from_last=True,
        )
        self.assertTrue(result.success)

        # location is stored in scheduling context but CalendarEvent
        # doesn't have a location field — just verify context was inherited
        ctx = ActionHandler._get_scheduling_context(self.user)
        self.assertEqual(ctx['location'], "Planet Fitness")

    def test_clone_inherits_event_type(self):
        """Clone inherits event_type when not explicitly set."""
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)

        handler.handle_create_event(
            title="Bible Study",
            start_date="2026-02-22",
            start_time="18:00",
            event_type="faith",
        )

        result = handler.handle_create_event(
            title="Bible Study",
            start_date="2026-02-24",
            clone_from_last=True,
            event_type="personal",  # default value from tool def
        )
        self.assertTrue(result.success)
        # After the clone, context should show faith (inherited)
        ctx = ActionHandler._get_scheduling_context(self.user)
        self.assertEqual(ctx['event_type'], 'faith')

    def test_clone_explicit_time_overrides_inherited(self):
        """When user provides explicit time during clone, it overrides."""
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)

        handler.handle_create_event(
            title="Workout",
            start_date="2026-02-22",
            start_time="06:15",
        )

        result = handler.handle_create_event(
            title="Workout",
            start_date="2026-02-24",
            start_time="07:00",  # explicit override
            clone_from_last=True,
        )
        self.assertTrue(result.success)

        from apps.calendar_engine.models import CalendarEvent
        event = CalendarEvent.objects.get(id=result.created_object['id'])
        eastern = pytz.timezone('America/New_York')
        local_start = event.start_dt.astimezone(eastern)
        self.assertEqual(local_start.hour, 7)
        self.assertEqual(local_start.minute, 0)

    def test_clone_without_prior_context_still_creates(self):
        """Clone without prior context creates event (no crash)."""
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)
        cache.clear()

        result = handler.handle_create_event(
            title="Workout",
            start_date="2026-02-24",
            clone_from_last=True,
        )
        # Should still succeed (as all-day since no time available)
        self.assertTrue(result.success)


class SafetyInvariantTests(TestCase):
    """Part 3: Runtime invariant checks."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='safety-test@example.com',
            password='testpass123',
            first_name='Safety',
        )
        prefs = self.user.preferences
        prefs.timezone = 'America/New_York'
        prefs.save()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_warning_logged_when_time_defaults_to_all_day(self):
        """If time is defaulted automatically, a warning is logged."""
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)

        with self.assertLogs('apps.ai.action_handlers', level='WARNING') as cm:
            handler.handle_create_event(
                title="Meeting",
                start_date="2026-02-22",
                # No start_time → will default to all-day
            )

        self.assertTrue(
            any('[SCHED] Time defaulted to all-day' in m for m in cm.output),
            f"Expected time-default warning in logs: {cm.output}"
        )

    def test_no_warning_when_start_time_provided(self):
        """No default-time warning when start_time is explicitly provided."""
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)

        # This should NOT produce the defaulting warning
        import logging
        with self.assertLogs('apps.ai.action_handlers', level='DEBUG') as cm:
            handler.handle_create_event(
                title="Meeting",
                start_date="2026-02-22",
                start_time="14:00",
            )

        # Filter for the specific warning
        default_warnings = [
            m for m in cm.output
            if 'Time defaulted to all-day' in m
        ]
        self.assertEqual(len(default_warnings), 0)

    def test_clone_assertion_passes_when_time_matches(self):
        """Clone assertion: cloned_event.time == original_event.time."""
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)

        handler.handle_create_event(
            title="Workout",
            start_date="2026-02-22",
            start_time="06:15",
        )

        # Clone — time should be inherited and assertion should pass
        with self.assertLogs('apps.ai.action_handlers', level='DEBUG') as cm:
            result = handler.handle_create_event(
                title="Workout",
                start_date="2026-02-24",
                clone_from_last=True,
            )

        self.assertTrue(result.success)
        self.assertTrue(
            any('Clone assertion passed' in m for m in cm.output),
            f"Expected clone assertion log: {cm.output}"
        )


class DebugLoggingTests(TestCase):
    """Part 4: Debug logging at scheduling decision points."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='debug-test@example.com',
            password='testpass123',
            first_name='Debug',
        )
        prefs = self.user.preferences
        prefs.timezone = 'America/Chicago'
        prefs.save()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_logs_base_local_datetime(self):
        """Debug log includes base local datetime."""
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)

        with self.assertLogs('apps.ai.action_handlers', level='DEBUG') as cm:
            handler.handle_create_event(
                title="Test",
                start_date="2026-02-22",
                start_time="10:00",
            )

        self.assertTrue(
            any('[SCHED] Base local datetime' in m for m in cm.output)
        )

    def test_logs_resolved_date(self):
        """Debug log includes resolved relative date."""
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)

        with self.assertLogs('apps.ai.action_handlers', level='DEBUG') as cm:
            handler.handle_create_event(
                title="Test",
                start_date="tomorrow",
                start_time="10:00",
            )

        self.assertTrue(
            any("Resolved 'tomorrow'" in m for m in cm.output)
        )

    def test_logs_timezone_used(self):
        """Debug log includes timezone used."""
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)

        with self.assertLogs('apps.ai.action_handlers', level='DEBUG') as cm:
            handler.handle_create_event(
                title="Test",
                start_date="2026-02-22",
                start_time="10:00",
            )

        self.assertTrue(
            any('America/Chicago' in m for m in cm.output)
        )

    def test_logs_clone_parameters(self):
        """Debug log includes clone parameter inheritance details."""
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)

        handler.handle_create_event(
            title="Workout",
            start_date="2026-02-22",
            start_time="06:15",
        )

        with self.assertLogs('apps.ai.action_handlers', level='DEBUG') as cm:
            handler.handle_create_event(
                title="Workout",
                start_date="2026-02-24",
                clone_from_last=True,
            )

        self.assertTrue(
            any('Clone mode: inheriting' in m for m in cm.output)
        )
        self.assertTrue(
            any('Inherited start_time=06:15' in m for m in cm.output)
        )

    def test_logs_final_event_details(self):
        """Debug log includes final event datetime details."""
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)

        with self.assertLogs('apps.ai.action_handlers', level='DEBUG') as cm:
            handler.handle_create_event(
                title="Test Event",
                start_date="2026-02-22",
                start_time="14:00",
            )

        self.assertTrue(
            any('[SCHED] Final event:' in m for m in cm.output)
        )


class CreateEventToolDefinitionTests(TestCase):
    """Verify the create_event tool definition includes clone_from_last."""

    def test_clone_from_last_in_tool_definition(self):
        """create_event tool definition includes clone_from_last parameter."""
        from apps.ai.intents.life_intents import LIFE_INTENT_TOOLS

        create_event_tool = None
        for tool in LIFE_INTENT_TOOLS:
            if tool['function']['name'] == 'create_event':
                create_event_tool = tool
                break

        self.assertIsNotNone(create_event_tool)
        props = create_event_tool['function']['parameters']['properties']
        self.assertIn('clone_from_last', props)
        self.assertEqual(props['clone_from_last']['type'], 'boolean')
