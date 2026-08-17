# ==============================================================================
# File: apps/ai/tests/test_object_reveal.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Object-Level Reveal — after a safe action creates an object THIS TURN, the CoS
#   reveals that SPECIFIC object (its get_absolute_url), not just the workspace, when the reveal
#   target contains it. Deterministic identity from the action result (no fuzzy resolution).
# ==============================================================================
from unittest.mock import patch

from django.test import TestCase

from apps.ai.cos_services.reveal import _object_in_workspace, resolve_reveal
from apps.core.action_router import ActionRoute, ActionType


def _route(url):
    return ActionRoute(action_type=ActionType.OPEN_WORKFLOW, destination_url=url,
                       destination_label="Fitness")


class ObjectInWorkspaceTests(TestCase):
    def test_object_inside_workspace(self):
        self.assertTrue(_object_in_workspace(
            "/health/physical/fitness/workout/123/", "/health/physical/fitness/"))
        # workspace resolved to a 'new' leaf still contains the object
        self.assertTrue(_object_in_workspace(
            "/health/physical/fitness/workout/123/", "/health/physical/fitness/workout/new/"))

    def test_object_in_different_workspace(self):
        self.assertFalse(_object_in_workspace(
            "/health/physical/fitness/workout/123/", "/health/physical/weight/"))
        self.assertFalse(_object_in_workspace(
            "/journal/42/", "/purpose/goals/"))

    def test_missing_urls(self):
        self.assertFalse(_object_in_workspace("", "/x/"))
        self.assertFalse(_object_in_workspace("/x/1/", ""))


class ResolveRevealObjectTests(TestCase):
    def test_upgrades_to_created_object_when_inside_workspace(self):
        created = {"url": "/health/physical/fitness/workout/123/", "label": "Morning Lift"}
        with patch("apps.core.action_router.resolve_route",
                   return_value=_route("/health/physical/fitness/workout/new/")):
            out = resolve_reveal(None, "my workout", current_url="/dashboard/",
                                 created_reveal=created)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["url"], "/health/physical/fitness/workout/123/")   # THE object
        self.assertTrue(out["object"])
        self.assertEqual(out["label"], "Morning Lift")

    def test_does_not_upgrade_when_target_is_a_different_workspace(self):
        # Created a workout, but asked to see WEIGHT → reveal the weight workspace, not the workout.
        created = {"url": "/health/physical/fitness/workout/123/", "label": "Morning Lift"}
        with patch("apps.core.action_router.resolve_route",
                   return_value=_route("/health/physical/weight/")):
            out = resolve_reveal(None, "my weight", current_url="/dashboard/",
                                 created_reveal=created)
        self.assertEqual(out["url"], "/health/physical/weight/")   # workspace, not the object
        self.assertFalse(out["object"])

    def test_no_created_object_is_plain_workspace_reveal(self):
        with patch("apps.core.action_router.resolve_route",
                   return_value=_route("/health/physical/fitness/")):
            out = resolve_reveal(None, "fitness", current_url="/dashboard/", created_reveal=None)
        self.assertEqual(out["url"], "/health/physical/fitness/")
        self.assertFalse(out["object"])

    def test_already_here_on_the_created_object(self):
        created = {"url": "/health/physical/fitness/workout/123/", "label": "Morning Lift"}
        with patch("apps.core.action_router.resolve_route",
                   return_value=_route("/health/physical/fitness/workout/new/")):
            out = resolve_reveal(None, "my workout",
                                 current_url="/health/physical/fitness/workout/123/",
                                 created_reveal=created)
        self.assertEqual(out["status"], "already_here")   # already viewing it → no navigation


class SafeAbsoluteUrlTests(TestCase):
    def test_returns_url_or_none_never_raises(self):
        from apps.ai.action_handlers import _safe_absolute_url

        class Ok:
            def get_absolute_url(self):
                return "/journal/7/"

        class Boom:
            def get_absolute_url(self):
                raise ValueError("no route")

        self.assertEqual(_safe_absolute_url(Ok()), "/journal/7/")
        self.assertIsNone(_safe_absolute_url(Boom()))
        self.assertIsNone(_safe_absolute_url(object()))   # no method at all


class RequestActionPropagatesCreatedObjectTests(TestCase):
    def test_created_object_carried_on_success(self):
        from apps.ai.cos_services import action_interface as ai
        env = {"status": "success", "message": "Logged.",
               "result": {"model": "WorkoutSession", "id": 5,
                          "url": "/health/physical/fitness/workout/5/"}}
        with patch.object(ai, "execute_action", return_value=env), \
             patch.object(ai, "record_tool_call"):
            out = ai.request_action(_FakeUser(), "log_workout", {})
        self.assertEqual(out["status"], ai.OK)
        self.assertEqual(out["created_object"]["url"], "/health/physical/fitness/workout/5/")


class _FakeUser:
    id = 1
    pk = 1
