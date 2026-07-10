# ==============================================================================
# File: apps/ai/tests/test_current_context_baseline.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Current Context baseline (Pillar 4) — the FAST tier ("what's happening now").
# ==============================================================================
"""
Tests for apps/ai/cos_services/current_context.py.

Current Context is the FAST tier: clock, current screen (structured page), capability
index. It does NOT own deterministic understanding (priority/patterns/etc. moved to the
Understanding tier). Structured page context is exposed; a missing page is a benign
'none', never "I can't see the screen".
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services.current_context import (
    CURRENT_CONTEXT_SCHEMA_VERSION,
    get_current_context_baseline,
)

User = get_user_model()


class CurrentContextBaselineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="cc@example.com", password="x")

    def test_shape_is_fast_tier_only(self):
        ctx = get_current_context_baseline(self.user)
        self.assertEqual(ctx["schema_version"], CURRENT_CONTEXT_SCHEMA_VERSION)
        self.assertEqual(set(ctx.keys()),
                         {"schema_version", "clock", "current_screen", "capabilities"})
        # No deterministic understanding leaks into Current Context.
        for banned in ("priority", "day_continuity", "patterns", "biggest_risk"):
            self.assertNotIn(banned, ctx)

    def test_clock_and_capabilities_present(self):
        ctx = get_current_context_baseline(self.user)
        self.assertIn("local_time", ctx["clock"])
        self.assertIn("part_of_day", ctx["clock"])
        self.assertIn("answerable_domains", ctx["capabilities"])

    def test_location_is_exposed_without_a_declared_focus(self):
        # WHERE the user is (navigation facts) is always safe to pass; with no declared
        # reference there is simply no focused object.
        page = {"url": "/faith/journey/today/", "module": "Faith",
                "page_title": "Today's Reading"}
        ctx = get_current_context_baseline(self.user, page_context=page)
        screen = ctx["current_screen"]
        self.assertEqual(screen["status"], "present")
        self.assertEqual(screen["location"]["url"], "/faith/journey/today/")
        self.assertEqual(screen["location"]["module"], "Faith")
        self.assertIsNone(screen["focus"])

    def test_declared_reference_resolves_to_canonical_truth(self):
        # The CONTRACT: page sends a reference; WLJ resolves the deterministic truth
        # server-side from the canonical model. Scraped DOM is never trusted.
        from apps.purpose.models import LifeGoal
        goal = LifeGoal.objects.create(
            user=self.user, title="Run a half marathon",
            description="Build to 13.1 miles by fall.",
            why_it_matters="Prove I can commit to something hard.",
        )
        page = {"url": f"/goals/{goal.pk}/", "module": "Goals",
                "focus_ref": f"purpose.lifegoal:{goal.pk}",
                # A scraped-content blob that must NOT be trusted as truth:
                "page_content": {"description": "SCRAPED-JUNK-SHOULD-BE-IGNORED"}}
        ctx = get_current_context_baseline(self.user, page_context=page)
        focus = ctx["current_screen"]["focus"]
        self.assertIsNotNone(focus)
        self.assertEqual(focus["source"], "canonical")
        self.assertEqual(focus["ref"], f"purpose.lifegoal:{goal.pk}")
        self.assertIn("Run a half marathon", focus["title"])
        self.assertIn("Prove I can commit", focus["content"])
        # Scraped junk never enters the truth WLJ hands the model.
        self.assertNotIn("SCRAPED-JUNK", json.dumps(ctx))

    def test_unowned_reference_is_reported_not_denied(self):
        # A declared reference to another user's object must not leak, and must not read
        # as "this does not exist" — it is a sync/ownership condition.
        from apps.purpose.models import LifeGoal
        other = User.objects.create_user(email="other@example.com", password="x")
        goal = LifeGoal.objects.create(user=other, title="Not my goal")
        page = {"url": f"/goals/{goal.pk}/", "module": "Goals",
                "focus_ref": f"purpose.lifegoal:{goal.pk}"}
        ctx = get_current_context_baseline(self.user, page_context=page)
        screen = ctx["current_screen"]
        self.assertIsNone(screen["focus"])
        self.assertIn("did not resolve", screen["note"])
        self.assertNotIn("Not my goal", json.dumps(ctx))

    def test_missing_page_is_benign_none_not_denial(self):
        ctx = get_current_context_baseline(self.user)  # no page_context
        self.assertEqual(ctx["current_screen"]["status"], "none")
        # never phrased as "cannot see"
        self.assertNotIn("cannot", json.dumps(ctx).lower())

    def test_output_is_json_safe(self):
        json.dumps(get_current_context_baseline(
            self.user, page_context={"page": "dashboard"}))
