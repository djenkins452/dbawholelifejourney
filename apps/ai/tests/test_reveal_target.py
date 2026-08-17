# ==============================================================================
# File: apps/ai/tests/test_reveal_target.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Reveal Target (navigate_to_workspace) tests. WLJ resolves a semantic target to
#   a workspace URL via the EXISTING destination authority (resolve_route/TeachingDestination),
#   owns the already-there relation, never invents a URL. Deterministic (mocks resolve_route so
#   the test does not depend on fixture data); tool-registration + already-here + not-found.
# ==============================================================================
from unittest.mock import patch

from django.test import TestCase

from apps.ai.cos_services.reveal import _same_workspace, resolve_reveal
from apps.core.action_router import ActionRoute, ActionType


def _route(url):
    return ActionRoute(action_type=ActionType.OPEN_WORKFLOW,
                       destination_url=url, destination_label="Weight Tracking")


class SameWorkspaceTests(TestCase):
    def test_path_slash_and_query_insensitive(self):
        self.assertTrue(_same_workspace("/health/weight/", "/health/weight"))
        self.assertTrue(_same_workspace("/dashboard/?date=2026-08-16", "/dashboard/"))
        self.assertFalse(_same_workspace("/health/weight/", "/health/glucose/"))
        self.assertFalse(_same_workspace("", "/x/"))


class ResolveRevealTests(TestCase):
    def test_ok_resolves_to_url(self):
        with patch("apps.core.action_router.resolve_route",
                   return_value=_route("/health/physical/weight/")):
            out = resolve_reveal(None, "my weight", current_url="/dashboard/")
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["url"], "/health/physical/weight/")
        self.assertEqual(out["label"], "Weight Tracking")

    def test_already_here_when_on_target(self):
        with patch("apps.core.action_router.resolve_route",
                   return_value=_route("/health/physical/weight/")):
            out = resolve_reveal(None, "my weight",
                                 current_url="/health/physical/weight/?range=6M")
        self.assertEqual(out["status"], "already_here")   # do NOT navigate

    def test_not_found_when_unresolvable(self):
        with patch("apps.core.action_router.resolve_route",
                   return_value=ActionRoute(action_type=ActionType.INFORMATIONAL)):
            out = resolve_reveal(None, "the moon", current_url=None)
        self.assertEqual(out["status"], "not_found")

    def test_blank_target_is_not_found(self):
        out = resolve_reveal(None, "   ", current_url=None)
        self.assertEqual(out["status"], "not_found")

    def test_resolver_exception_is_honest(self):
        with patch("apps.core.action_router.resolve_route",
                   side_effect=RuntimeError("boom")):
            out = resolve_reveal(None, "weight", current_url=None)
        self.assertEqual(out["status"], "not_found")


class RevealToolRegistrationTests(TestCase):
    def test_navigate_tool_always_available_even_read_only(self):
        from apps.ai.model_interface.constitution import all_tools
        for writes in (True, False):
            names = {t["function"]["name"] for t in all_tools(writes_enabled=writes)}
            self.assertIn("navigate_to_workspace", names,
                          f"reveal tool must be available (writes_enabled={writes})")
