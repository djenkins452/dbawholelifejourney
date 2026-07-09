# ==============================================================================
# File: apps/ai/tests/test_current_context_baseline.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Current Context baseline (Pillar 4) — minimal always-on projection.
# ==============================================================================
"""
Tests for apps/ai/cos_services/current_context.py.

Locks in: the baseline ships clock + capabilities always; clinical-safety policy and
day-continuity come from injected pre-warmed inputs (pending when absent — never live-
computed); NO headline/narrative is ever emitted; output is JSON-safe.
"""

import json
from types import SimpleNamespace

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

    def test_clock_and_capabilities_always_present(self):
        ctx = get_current_context_baseline(self.user)
        self.assertEqual(ctx["schema_version"], CURRENT_CONTEXT_SCHEMA_VERSION)
        self.assertIn("local_time", ctx["clock"])
        self.assertIn("part_of_day", ctx["clock"])
        self.assertIn("answerable_domains", ctx["capabilities"])

    def test_never_emits_a_headline_or_narrative(self):
        # The baseline is facts + policy only. Reasoning artifacts must be absent.
        signals = SimpleNamespace(
            health_critical=[{"text": "Take Metformin — overdue", "kind": "health_critical"}],
            priority_action={"text": "Take Metformin", "kind": "health_critical"},
            headline="Recovery is your priority today",  # must NOT leak through
        )
        ctx = get_current_context_baseline(self.user, signals=signals)
        flat = json.dumps(ctx).lower()
        self.assertNotIn("headline", flat)
        self.assertNotIn("recovery is your priority", flat)

    def test_pending_when_signals_and_continuity_absent(self):
        ctx = get_current_context_baseline(self.user)
        self.assertEqual(ctx["priority"]["status"], "pending")
        self.assertEqual(ctx["day_continuity"]["status"], "pending")

    def test_clinical_safety_policy_from_injected_signals(self):
        signals = SimpleNamespace(
            health_critical=[{"text": "Take Metformin — overdue since 8:00 AM",
                              "kind": "health_critical"}],
            priority_action={"text": "Take Metformin", "kind": "health_critical"},
        )
        ctx = get_current_context_baseline(self.user, signals=signals)
        self.assertEqual(ctx["priority"]["status"], "ok")
        self.assertEqual(len(ctx["priority"]["clinical_safety"]), 1)
        self.assertIn("do not re-rank", ctx["priority"]["note"])
        self.assertEqual(ctx["priority"]["priority_action"]["kind"], "health_critical")

    def test_day_continuity_from_injected_decision(self):
        continuity = SimpleNamespace(
            mode="reorient_delta",
            material_changes=[{"what": "sleep dropped to 5h"}],
        )
        ctx = get_current_context_baseline(self.user, continuity=continuity)
        self.assertEqual(ctx["day_continuity"]["status"], "ok")
        self.assertEqual(ctx["day_continuity"]["mode"], "reorient_delta")
        self.assertEqual(len(ctx["day_continuity"]["material_changes"]), 1)

    def test_output_is_json_safe(self):
        signals = SimpleNamespace(health_critical=[], priority_action=None)
        continuity = SimpleNamespace(mode="continue", material_changes=[])
        ctx = get_current_context_baseline(self.user, signals=signals, continuity=continuity)
        json.dumps(ctx)  # raises if not serializable
