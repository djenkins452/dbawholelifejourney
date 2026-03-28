# ==============================================================================
# File: apps/core/ai_events/tests/test_router_integration.py
# Project: Whole Life Journey
# Description: Tests for event query routes in deterministic router
# ==============================================================================

from datetime import date, time, timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.health.models import Medicine, MedicineLog, MedicineSchedule
from apps.users.models import User, TermsAcceptance


class EventRouterIntegrationTestBase(TestCase):
    """Base with test user and medicine data."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='testroutervent@example.com',
            password='testpass123',
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        # Create medicine with a missed dose
        self.medicine = Medicine.objects.create(
            user=self.user,
            name='Lantus SoloStar',
            dose='10 units',
            frequency='daily',
            medicine_status=Medicine.STATUS_ACTIVE,
            start_date=date.today() - timedelta(days=30),
        )
        self.schedule = MedicineSchedule.objects.create(
            medicine=self.medicine,
            scheduled_time=time(9, 0),
            time_of_day='morning',
            is_active=True,
        )


class EventMissedRouteTest(EventRouterIntegrationTestBase):
    """Test that 'what did I miss?' routes to event access layer."""

    def test_what_did_i_miss_routes_deterministically(self):
        """The exact scenario from the screenshot."""
        from apps.ai.deterministic_router import classify_and_route

        # Create a missed dose 3 days ago
        missed_date = date.today() - timedelta(days=3)
        MedicineLog.objects.create(
            user=self.user,
            medicine=self.medicine,
            schedule=self.schedule,
            scheduled_date=missed_date,
            scheduled_time=time(9, 0),
            log_status=MedicineLog.STATUS_MISSED,
        )

        result = classify_and_route("What did I miss?", self.user)

        # Should be terminal (no LLM needed)
        self.assertTrue(result.is_terminal)
        self.assertEqual(result.route_name, 'event_missed_query')
        self.assertIsNotNone(result.response)
        # Response should contain the medicine name
        self.assertIn('Lantus SoloStar', result.response)

    def test_missed_medication_specific(self):
        from apps.ai.deterministic_router import classify_and_route

        missed_date = date.today() - timedelta(days=2)
        MedicineLog.objects.create(
            user=self.user,
            medicine=self.medicine,
            schedule=self.schedule,
            scheduled_date=missed_date,
            scheduled_time=time(9, 0),
            log_status=MedicineLog.STATUS_MISSED,
        )

        result = classify_and_route("Which medication did I miss?", self.user)
        self.assertTrue(result.is_terminal)
        self.assertIn('Lantus SoloStar', result.response)

    def test_nothing_missed_returns_positive_message(self):
        from apps.ai.deterministic_router import classify_and_route

        # No missed doses — only taken
        MedicineLog.objects.create(
            user=self.user,
            medicine=self.medicine,
            schedule=self.schedule,
            scheduled_date=date.today(),
            scheduled_time=time(9, 0),
            log_status=MedicineLog.STATUS_TAKEN,
            taken_at=timezone.now(),
        )

        result = classify_and_route("What did I miss?", self.user)
        self.assertTrue(result.is_terminal)
        self.assertIn('on track', result.response.lower())


class EventTimelineRouteTest(EventRouterIntegrationTestBase):
    """Test that timeline queries route correctly."""

    def test_what_happened_yesterday(self):
        from apps.ai.deterministic_router import classify_and_route

        yesterday = date.today() - timedelta(days=1)
        MedicineLog.objects.create(
            user=self.user,
            medicine=self.medicine,
            schedule=self.schedule,
            scheduled_date=yesterday,
            scheduled_time=time(9, 0),
            log_status=MedicineLog.STATUS_TAKEN,
            taken_at=timezone.now() - timedelta(days=1),
        )

        result = classify_and_route("What happened yesterday?", self.user)
        self.assertTrue(result.is_terminal)
        self.assertEqual(result.route_name, 'event_timeline_query')
        self.assertIn('yesterday', result.response.lower())


class EventSlippageRouteTest(EventRouterIntegrationTestBase):
    """Test that slippage queries route correctly."""

    def test_routine_slipping_routes(self):
        from apps.ai.deterministic_router import classify_and_route

        result = classify_and_route(
            "When did my routine start slipping?", self.user,
        )
        self.assertTrue(result.is_terminal)
        self.assertEqual(result.route_name, 'event_slippage_query')
        self.assertIsNotNone(result.response)


class ExistingRoutesUnbrokenTest(EventRouterIntegrationTestBase):
    """CRITICAL: Verify that existing routes still work correctly."""

    def test_medication_status_query_still_works(self):
        """'Did I take my meds?' should still route to existing medication_query."""
        from apps.ai.deterministic_router import classify_and_route

        result = classify_and_route("Did I take my meds?", self.user)
        # Should NOT hit event routes — different phrase set
        self.assertNotEqual(result.route_name, 'event_missed_query')

    def test_next_action_still_works(self):
        """'What should I do next?' should still route to next_action."""
        from apps.ai.deterministic_router import classify_and_route

        result = classify_and_route("What should I do next?", self.user)
        self.assertEqual(result.route_name, 'next_action')

    def test_how_am_i_doing_falls_through(self):
        """General conversational messages should still fall through."""
        from apps.ai.deterministic_router import classify_and_route

        result = classify_and_route("How am I doing?", self.user)
        # Should NOT match any event route
        self.assertNotIn(result.route_name, [
            'event_missed_query',
            'event_timeline_query',
            'event_slippage_query',
        ])

    def test_log_weight_falls_through(self):
        """Action messages should not be intercepted by event routes."""
        from apps.ai.deterministic_router import classify_and_route

        result = classify_and_route("Log my weight at 185 lbs", self.user)
        self.assertNotIn(result.route_name, [
            'event_missed_query',
            'event_timeline_query',
            'event_slippage_query',
        ])
