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

    def test_structured_page_context_is_exposed(self):
        page = {"page": "faith_home", "focused": {"prayer_completed": True,
                                                  "bible_reading_completed": True}}
        ctx = get_current_context_baseline(self.user, page_context=page)
        self.assertEqual(ctx["current_screen"]["status"], "present")
        self.assertEqual(ctx["current_screen"]["page"]["page"], "faith_home")
        self.assertTrue(ctx["current_screen"]["page"]["focused"]["prayer_completed"])

    def test_missing_page_is_benign_none_not_denial(self):
        ctx = get_current_context_baseline(self.user)  # no page_context
        self.assertEqual(ctx["current_screen"]["status"], "none")
        # never phrased as "cannot see"
        self.assertNotIn("cannot", json.dumps(ctx).lower())

    def test_output_is_json_safe(self):
        json.dumps(get_current_context_baseline(
            self.user, page_context={"page": "dashboard"}))
