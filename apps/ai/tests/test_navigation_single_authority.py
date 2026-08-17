# ==============================================================================
# File: apps/ai/tests/test_navigation_single_authority.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Navigation cleanup — ONE deterministic navigation authority. The legacy
#   PersonalAssistant post-action "View it" hint is now resolved by resolve_route()/
#   TeachingDestination (the SAME registry the certified CoS Reveal Target uses), NOT a
#   local {action→url} map. Tests the DELEGATION invariant (mocking the authority, since
#   the test DB has no TeachingDestination fixtures) + concept derivation + object URLs.
# ==============================================================================
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.core.action_router import ActionRoute, ActionType
from apps.users.models import TermsAcceptance

try:
    from apps.users.models import User
except ImportError:
    from django.contrib.auth import get_user_model
    User = get_user_model()


def _user(email="nav@test.com"):
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    return u


class NavigationSingleAuthorityTests(TestCase):
    def setUp(self):
        self.user = _user()
        from apps.ai.personal_assistant import PersonalAssistant
        self.pa = PersonalAssistant(self.user)

    def test_local_navigation_map_is_retired(self):
        from apps.ai.personal_assistant import PersonalAssistant
        self.assertFalse(hasattr(PersonalAssistant, "NAVIGATION_HINTS"),
                         "NAVIGATION_HINTS must be retired in favor of resolve_route")

    def test_concept_derivation_strips_verb(self):
        from apps.ai.personal_assistant import PersonalAssistant
        cases = {"log_weight": "weight", "create_task": "task",
                 "mutate_calendar_event": "calendar event", "log_heart_rate": "heart rate",
                 "complete_task": "task", "create_habit": "habit"}
        for at, concept in cases.items():
            self.assertEqual(PersonalAssistant._nav_concept_for_action(at), concept)

    def test_hint_delegates_to_resolve_route(self):
        # The URL comes from resolve_route (single authority), not a local map.
        route = ActionRoute(action_type=ActionType.OPEN_WORKFLOW,
                            destination_url="/health/physical/weight/",
                            destination_label="Weight Tracking")
        with patch("apps.core.action_router.resolve_route", return_value=route) as m:
            hint = self.pa._get_navigation_hint([{"type": "log_weight", "success": True}])
        m.assert_called_once()
        self.assertEqual(m.call_args.kwargs.get("text"), "weight")   # derived concept
        self.assertEqual(hint, {"url": "/health/physical/weight/", "label": "View it",
                                "action_type": "log_weight"})

    def test_unresolvable_yields_no_guessed_url(self):
        with patch("apps.core.action_router.resolve_route",
                   return_value=ActionRoute(action_type=ActionType.INFORMATIONAL)):
            hint = self.pa._get_navigation_hint([{"type": "frobnicate_widget", "success": True}])
        self.assertIsNone(hint)

    def test_unsuccessful_action_yields_no_hint(self):
        with patch("apps.core.action_router.resolve_route") as m:
            hint = self.pa._get_navigation_hint([{"type": "log_weight", "success": False}])
        self.assertIsNone(hint)
        m.assert_not_called()   # never even consults the authority for a failed action

    def test_resolver_exception_is_safe(self):
        with patch("apps.core.action_router.resolve_route", side_effect=RuntimeError("x")):
            hint = self.pa._get_navigation_hint([{"type": "log_weight", "success": True}])
        self.assertIsNone(hint)   # never raises, never a guessed URL


class ObjectAddressabilityTests(TestCase):
    """get_absolute_url on the top health objects → addressable for object-level Reveal."""

    def test_workout_and_intake_have_absolute_urls(self):
        from apps.health.models import Intake, WorkoutSession
        w = WorkoutSession(pk=42)
        self.assertEqual(w.get_absolute_url(), reverse("health:workout_detail", args=[42]))
        i = Intake(pk=7)
        self.assertEqual(i.get_absolute_url(), reverse("health:intake_detail", args=[7]))
