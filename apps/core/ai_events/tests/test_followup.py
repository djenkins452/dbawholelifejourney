# ==============================================================================
# File: apps/core/ai_events/tests/test_followup.py
# Project: Whole Life Journey
# Description: Tests for multi-turn event follow-up resolution
# ==============================================================================

from datetime import date, time, timedelta
from unittest.mock import MagicMock

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_events.followup import (
    EVENT_CONTEXT_MAX_TURNS,
    EVENT_CONTEXT_TTL_MINUTES,
    clear_event_context,
    get_event_context,
    increment_turn_count,
    is_followup_query,
    resolve_followup,
    store_event_context,
)
from apps.core.ai_events.event_record import EventRecord
from apps.ai.models import AssistantConversation
from apps.users.models import User, TermsAcceptance


class FollowUpDetectionTest(TestCase):
    """Test follow-up query detection."""

    # ── Should match ──

    def test_what_date_was_that(self):
        self.assertTrue(is_followup_query("what date was that"))

    def test_when_was_that(self):
        self.assertTrue(is_followup_query("when was that"))

    def test_was_that_yesterday(self):
        self.assertTrue(is_followup_query("was that yesterday"))

    def test_which_medication(self):
        self.assertTrue(is_followup_query("which medication was it"))

    def test_which_one(self):
        self.assertTrue(is_followup_query("which one"))

    def test_what_time(self):
        self.assertTrue(is_followup_query("what time was it"))

    def test_how_many_days_ago(self):
        self.assertTrue(is_followup_query("how many days ago"))

    def test_what_date_did_i_miss(self):
        self.assertTrue(is_followup_query("what date did i miss it"))

    # ── Should NOT match ──

    def test_general_question(self):
        self.assertFalse(is_followup_query("how am i doing"))

    def test_new_event_query(self):
        self.assertFalse(is_followup_query("what did i miss"))

    def test_action_request(self):
        self.assertFalse(is_followup_query("log my weight at 185"))

    def test_greeting(self):
        self.assertFalse(is_followup_query("good morning"))


class EventContextStorageTest(TestCase):
    """Test event context storage in conversation metadata."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='testfollowup@example.com',
            password='testpass123',
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        self.conversation = AssistantConversation.objects.create(
            user=self.user,
            title='Test Conversation',
        )

    def _make_event(self, **kwargs):
        defaults = {
            'domain': 'medication',
            'event_type': 'dose_missed',
            'timestamp': timezone.now(),
            'label': 'Lantus SoloStar — 9:00 AM',
            'status': 'missed',
            'detail': {
                'medicine_name': 'Lantus SoloStar',
                'dose': '10 units',
                'scheduled_date': str(date.today() - timedelta(days=3)),
                'scheduled_time': '09:00:00',
                'log_status': 'missed',
            },
        }
        defaults.update(kwargs)
        return EventRecord(**defaults)

    def test_store_and_retrieve(self):
        events = [self._make_event()]
        store_event_context(
            self.conversation,
            'event_missed_query',
            events,
            'You missed 1 dose.',
        )

        ctx = get_event_context(self.conversation)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx['route_name'], 'event_missed_query')
        self.assertEqual(ctx['event_count'], 1)
        self.assertEqual(ctx['events'][0]['detail']['medicine_name'], 'Lantus SoloStar')

    def test_ttl_expiration(self):
        events = [self._make_event()]
        store_event_context(
            self.conversation, 'event_missed_query', events, 'test',
        )

        # Manually set created_at to past TTL
        metadata = self.conversation.metadata
        old_time = (timezone.now() - timedelta(minutes=EVENT_CONTEXT_TTL_MINUTES + 5))
        metadata['recent_event_context']['created_at'] = old_time.isoformat()
        self.conversation.metadata = metadata
        self.conversation.save(update_fields=['metadata'])

        ctx = get_event_context(self.conversation)
        self.assertIsNone(ctx)

    def test_turn_expiration(self):
        events = [self._make_event()]
        store_event_context(
            self.conversation, 'event_missed_query', events, 'test',
        )

        # Increment past max turns
        for _ in range(EVENT_CONTEXT_MAX_TURNS + 1):
            increment_turn_count(self.conversation)
            self.conversation.refresh_from_db()

        ctx = get_event_context(self.conversation)
        self.assertIsNone(ctx)

    def test_increment_turn_count(self):
        events = [self._make_event()]
        store_event_context(
            self.conversation, 'event_missed_query', events, 'test',
        )

        increment_turn_count(self.conversation)
        self.conversation.refresh_from_db()

        ctx = get_event_context(self.conversation)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx['turns_since'], 1)

    def test_clear_context(self):
        events = [self._make_event()]
        store_event_context(
            self.conversation, 'event_missed_query', events, 'test',
        )

        clear_event_context(self.conversation)
        self.conversation.refresh_from_db()

        ctx = get_event_context(self.conversation)
        self.assertIsNone(ctx)


class FollowUpResolutionTest(TestCase):
    """Test deterministic follow-up resolution."""

    def setUp(self):
        self.missed_date = str(date.today() - timedelta(days=3))
        self.event_context = {
            'route_name': 'event_missed_query',
            'events': [{
                'domain': 'medication',
                'event_type': 'dose_missed',
                'timestamp': timezone.now().isoformat(),
                'label': 'Lantus SoloStar — 9:00 AM',
                'status': 'missed',
                'detail': {
                    'medicine_name': 'Lantus SoloStar',
                    'dose': '10 units',
                    'scheduled_date': self.missed_date,
                    'scheduled_time': '09:00:00',
                    'log_status': 'missed',
                },
                'source_model': 'MedicineLog',
                'source_id': 42,
            }],
            'event_count': 1,
            'response_text': 'You missed 1 dose.',
            'created_at': timezone.now().isoformat(),
            'turns_since': 0,
        }

    def test_resolve_date_question(self):
        result = resolve_followup("what date was that", self.event_context)
        self.assertIsNotNone(result)
        # Result contains either the day name (if < 7 days) or a formatted date
        self.assertIn("**", result)  # Has bold formatting
        self.assertTrue(
            any(word in result.lower() for word in [
                'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
                'saturday', 'sunday', 'today', 'yesterday', 'march',
                'february', 'january',
            ]),
            f"Expected a date reference in: {result}"
        )

    def test_resolve_was_that_yesterday_no(self):
        result = resolve_followup("was that yesterday", self.event_context)
        self.assertIsNotNone(result)
        self.assertIn("No", result)
        self.assertIn("3 days ago", result)

    def test_resolve_was_that_yesterday_yes(self):
        yesterday = str(date.today() - timedelta(days=1))
        self.event_context['events'][0]['detail']['scheduled_date'] = yesterday
        result = resolve_followup("was that yesterday", self.event_context)
        self.assertIsNotNone(result)
        self.assertIn("Yes", result)

    def test_resolve_which_medication(self):
        result = resolve_followup("which medication was it", self.event_context)
        self.assertIsNotNone(result)
        self.assertIn("Lantus SoloStar", result)
        self.assertIn("10 units", result)

    def test_resolve_what_time(self):
        result = resolve_followup("what time was it", self.event_context)
        self.assertIsNotNone(result)
        self.assertIn("09:00:00", result)

    def test_resolve_how_many_days_ago(self):
        result = resolve_followup("how many days ago", self.event_context)
        self.assertIsNotNone(result)
        self.assertIn("3 days ago", result)

    def test_unresolvable_returns_none(self):
        result = resolve_followup("tell me about the weather", self.event_context)
        self.assertIsNone(result)

    def test_empty_events_returns_none(self):
        self.event_context['events'] = []
        result = resolve_followup("what date was that", self.event_context)
        self.assertIsNone(result)


class FollowUpRouterIntegrationTest(TestCase):
    """Test that follow-ups route correctly through the deterministic router."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='testfollowroute@example.com',
            password='testpass123',
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        self.conversation = AssistantConversation.objects.create(
            user=self.user,
            title='Test Follow-Up',
        )

    def test_followup_with_stored_context(self):
        """Full multi-turn scenario: event query → follow-up."""
        from apps.ai.deterministic_router import classify_and_route
        from apps.health.models import Medicine, MedicineLog, MedicineSchedule

        # Create missed dose
        medicine = Medicine.objects.create(
            user=self.user,
            name='Lantus SoloStar',
            dose='10 units',
            frequency='daily',
            medicine_status=Medicine.STATUS_ACTIVE,
            start_date=date.today() - timedelta(days=30),
        )
        schedule = MedicineSchedule.objects.create(
            medicine=medicine,
            scheduled_time=time(9, 0),
            time_of_day='morning',
            is_active=True,
        )
        missed_date = date.today() - timedelta(days=3)
        MedicineLog.objects.create(
            user=self.user,
            medicine=medicine,
            schedule=schedule,
            scheduled_date=missed_date,
            scheduled_time=time(9, 0),
            log_status=MedicineLog.STATUS_MISSED,
        )

        # Turn 1: "What did I miss?"
        result1 = classify_and_route(
            "What did I miss?", self.user, conversation=self.conversation,
        )
        self.assertTrue(result1.is_terminal)
        self.assertEqual(result1.route_name, 'event_missed_query')
        self.assertIn('Lantus SoloStar', result1.response)

        # Store event context (normally done by personal_assistant.py)
        from apps.ai.deterministic_router import get_stashed_events
        from apps.core.ai_events.followup import store_event_context
        stashed = get_stashed_events()
        if stashed:
            store_event_context(
                self.conversation, result1.route_name, stashed, result1.response,
            )
        self.conversation.refresh_from_db()

        # Turn 2: "What date was that?"
        result2 = classify_and_route(
            "What date was that?", self.user, conversation=self.conversation,
        )
        self.assertTrue(result2.is_terminal)
        self.assertEqual(result2.route_name, 'event_followup')
        self.assertIsNotNone(result2.response)

    def test_followup_without_context_falls_through(self):
        """Follow-up pattern without stored context should fall through."""
        from apps.ai.deterministic_router import classify_and_route

        result = classify_and_route(
            "What date was that?", self.user, conversation=self.conversation,
        )
        # Should NOT match event_followup (no context stored)
        self.assertNotEqual(result.route_name, 'event_followup')

    def test_existing_routes_still_work_with_conversation(self):
        """Passing conversation should not break existing routes."""
        from apps.ai.deterministic_router import classify_and_route

        result = classify_and_route(
            "What should I do next?", self.user, conversation=self.conversation,
        )
        self.assertEqual(result.route_name, 'next_action')
