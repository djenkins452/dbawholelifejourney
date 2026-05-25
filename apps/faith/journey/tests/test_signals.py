"""
Tests for the six Journey signals.

Each signal asserts the expected event_type is emitted via the WLJ domain
events bus. The bus is patched at the location of the import (inside
apps.faith.journey.signals._safe_emit) so we capture every emission.
"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.faith.journey.models import (
    JourneyArc,
    JourneyDay,
    JourneyPath,
    UserJourney,
    UserJourneyDayProgress,
)
from apps.faith.journey.services import mark_day_complete


User = get_user_model()


def _u(email="signals@example.com"):
    from apps.users.models import TermsAcceptance
    from django.conf import settings
    user = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class SignalEmissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_journey_path", "walking_with_god")
        cls.path = JourneyPath.objects.get(slug="walking_with_god")
        cls.arc = JourneyArc.objects.get(slug="egypt_to_tabernacle")
        cls.day15 = JourneyDay.objects.get(arc=cls.arc, day_number=15)

    def _captured(self, patched_emit):
        """Helper: list of (event_type, data) for each call to safe_emit_event."""
        return [
            (call.kwargs.get("event_type") or call.args[0], call.kwargs.get("data", {}))
            for call in patched_emit.call_args_list
        ]

    def _patch_emit(self):
        return mock.patch("apps.faith.journey.signals.safe_emit_event")

    # ---------------------------------------------------------------------- starts

    def test_journey_started_fires_on_user_journey_creation(self):
        user = _u("started@example.com")
        with mock.patch("apps.core.events.domain_events.safe_emit_event") as patched_emit:
            UserJourney.objects.create(
                user=user, journey_path=self.path, current_arc=self.arc, current_day_number=15,
            )
            events = [c.args[0] for c in patched_emit.call_args_list]
            self.assertIn("journey.started", events)

    def test_journey_started_does_not_fire_on_update(self):
        user = _u("started2@example.com")
        uj = UserJourney.objects.create(
            user=user, journey_path=self.path, current_arc=self.arc, current_day_number=15,
        )
        with mock.patch("apps.core.events.domain_events.safe_emit_event") as patched_emit:
            uj.preferred_difficulty = "deeper"
            uj.save()
            events = [c.args[0] for c in patched_emit.call_args_list]
            self.assertNotIn("journey.started", events)

    # ---------------------------------------------------------------- day completed

    def test_day_completed_fires_only_on_false_to_true_transition(self):
        user = _u("daycomp@example.com")
        uj = UserJourney.objects.create(
            user=user, journey_path=self.path, current_arc=self.arc, current_day_number=15,
        )
        with mock.patch("apps.core.events.domain_events.safe_emit_event") as patched_emit:
            # First save: is_completed False — no event
            progress = UserJourneyDayProgress.objects.create(
                user=user, user_journey=uj, journey_day=self.day15, is_completed=False,
            )
            events_after_create = [c.args[0] for c in patched_emit.call_args_list]
            self.assertNotIn("journey.day.completed", events_after_create)

            # Flip to True: event fires once
            progress.is_completed = True
            progress.save()
            events_after_flip = [c.args[0] for c in patched_emit.call_args_list]
            self.assertEqual(events_after_flip.count("journey.day.completed"), 1)

            # Re-saving with no change: no additional fire
            progress.reflection_notes = "edited"
            progress.save()
            events_after_resave = [c.args[0] for c in patched_emit.call_args_list]
            self.assertEqual(events_after_resave.count("journey.day.completed"), 1)

    # -------------------------------------------------- application committed

    def test_application_committed_fires_only_on_transition(self):
        user = _u("appcomp@example.com")
        uj = UserJourney.objects.create(
            user=user, journey_path=self.path, current_arc=self.arc, current_day_number=15,
        )
        with mock.patch("apps.core.events.domain_events.safe_emit_event") as patched_emit:
            progress = UserJourneyDayProgress.objects.create(
                user=user, user_journey=uj, journey_day=self.day15, application_committed=False,
            )
            self.assertNotIn("journey.application.committed", [c.args[0] for c in patched_emit.call_args_list])
            progress.application_committed = True
            progress.save()
            events = [c.args[0] for c in patched_emit.call_args_list]
            self.assertEqual(events.count("journey.application.committed"), 1)

    # -------------------------------------------------- arc completed (service)

    def test_arc_completed_fires_when_last_day_marked_complete(self):
        """Day 15 is currently the only authored day. Completing it = arc done."""
        user = _u("arccomp@example.com")
        uj = UserJourney.objects.create(
            user=user, journey_path=self.path, current_arc=self.arc, current_day_number=15,
        )
        with mock.patch("apps.core.events.domain_events.safe_emit_event") as patched_emit:
            mark_day_complete(uj, self.day15, reflection_notes="done", application_committed=False)
            events = [c.args[0] for c in patched_emit.call_args_list]
            self.assertIn("journey.arc.completed", events)

    # -------------------------------------------------- confusion flagged (view)

    def test_confusion_flagged_endpoint_emits_signal(self):
        user = _u("confusion@example.com")
        client = Client()
        client.force_login(user)
        UserJourney.objects.create(
            user=user, journey_path=self.path, current_arc=self.arc, current_day_number=15,
        )
        with mock.patch("apps.core.events.domain_events.safe_emit_event") as patched_emit:
            resp = client.post(
                reverse("journey:confusion_flagged"),
                data='{"arc_slug":"egypt_to_tabernacle","day_number":15,"topic":"Why are there sacrifices?"}',
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 204)
            events = [c.args[0] for c in patched_emit.call_args_list]
            self.assertIn("journey.confusion.flagged", events)

    # -------------------------------------------------- resumed (view)

    def test_resumed_fires_when_user_returns_after_three_day_gap(self):
        user = _u("resumed@example.com")
        client = Client()
        client.force_login(user)
        uj = UserJourney.objects.create(
            user=user, journey_path=self.path, current_arc=self.arc, current_day_number=15,
            last_visited_at=timezone.now() - timedelta(days=5),
        )
        with mock.patch("apps.core.events.domain_events.safe_emit_event") as patched_emit:
            resp = client.get(reverse("journey:today"))
            self.assertEqual(resp.status_code, 200)
            events = [c.args[0] for c in patched_emit.call_args_list]
            self.assertIn("journey.resumed", events)

    def test_resumed_does_not_fire_for_short_gap(self):
        user = _u("noresume@example.com")
        client = Client()
        client.force_login(user)
        uj = UserJourney.objects.create(
            user=user, journey_path=self.path, current_arc=self.arc, current_day_number=15,
            last_visited_at=timezone.now() - timedelta(hours=12),
        )
        with mock.patch("apps.core.events.domain_events.safe_emit_event") as patched_emit:
            client.get(reverse("journey:today"))
            events = [c.args[0] for c in patched_emit.call_args_list]
            self.assertNotIn("journey.resumed", events)
