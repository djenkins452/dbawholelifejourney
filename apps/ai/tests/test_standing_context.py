# ==============================================================================
# File: apps/ai/tests/test_standing_context.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for the ChatGPT CoS StandingContextService (Phase 1)
# ==============================================================================
"""
StandingContextService tests.

Verifies the always-loaded ChatGPT CoS context:
* CACHE-FIRST / NEVER live-compute on the request path (pending on a miss).
* `allow_build=True` warms via the existing prewarm (background callers only).
* Ready projection reuses cos_context + executive (no fabrication).
* Output is always JSON-serializable (it is read by an external LLM).
* The cos_context refactor (build_executive_from_context) is a pure projection.
"""

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services import get_standing_context, STANDING_CONTEXT_SCHEMA_VERSION

User = get_user_model()

_CACHE_FN = "apps.ai.readiness_cache.get_cached_cos_context"
_BUILD_FN = "apps.ai.readiness_cache.prewarm_cos_context"


def _fake_context():
    """A minimal but realistic cos_context (only public keys, as cached)."""
    return {
        "module_permissions": {"health": True, "faith": True, "finance": False},
        "top_signals": [{"type": "glucose_high", "severity": "warning"}],
        "critical_signals": [],
        "user_priorities": ["Finish report", "Call doctor"],
        "right_now_focus": {"active_block": "morning_routine", "focus": "hydration"},
        "execution_summaries": {"done": 2, "overdue": 1, "next": "Take meds"},
        "capacity_snapshot": {"completed_blocks": 2, "total_blocks": 5},
        "cos_intelligence": {"overall": "steady"},
        "day_significance": "normal",
        "calendar_events_today": [{"title": "Standup", "time": "09:00"}],
        "medication_adherence_state": {"adherence_7d": 0.85},
        "active_fast_status": {"active": False},
        "alignment_score": 90,
        "drift_score": 5,
    }


class StandingContextServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="standing@example.com", password="x"
        )
        # Ensure preferences exist for cos_name resolution.
        if not hasattr(cls.user, "preferences") or cls.user.preferences is None:
            from apps.users.models import UserPreferences
            UserPreferences.objects.get_or_create(user=cls.user)

    # --- no live compute on request path ---------------------------------
    def test_pending_on_cache_miss_does_not_build(self):
        with mock.patch(_CACHE_FN, return_value=None) as cache_fn, \
             mock.patch(_BUILD_FN) as build_fn:
            result = get_standing_context(self.user)  # allow_build defaults False
        self.assertEqual(result["status"], "pending")
        cache_fn.assert_called_once()
        build_fn.assert_not_called()  # NEVER live-compute on the request path
        self.assertEqual(result["schema_version"], STANDING_CONTEXT_SCHEMA_VERSION)
        self.assertIn("trust_framing", result)

    def test_allow_build_warms_on_miss(self):
        with mock.patch(_CACHE_FN, return_value=None), \
             mock.patch(_BUILD_FN, return_value=_fake_context()) as build_fn:
            result = get_standing_context(self.user, allow_build=True)
        build_fn.assert_called_once()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["_meta"]["source"], "build")

    # --- ready projection -------------------------------------------------
    def test_ready_projection_from_cache(self):
        with mock.patch(_CACHE_FN, return_value=_fake_context()):
            result = get_standing_context(self.user)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["_meta"]["source"], "cache")
        # reused fields are surfaced (not fabricated)
        self.assertEqual(result["active_block"], "morning_routine")
        self.assertEqual(result["execution_summary"]["overdue"], 1)
        self.assertEqual(result["priorities"], ["Finish report", "Call doctor"])
        self.assertEqual(result["cos_intelligence"], {"overall": "steady"})
        # executive projection ran
        self.assertIsInstance(result["strategic_summary"], str)
        self.assertIn("current_mode", result)
        # explicit gaps, not fabrication
        self.assertIsNone(result["travel_state"])

    def test_personalization_resolves_cos_name_and_modules(self):
        with mock.patch(_CACHE_FN, return_value=_fake_context()):
            result = get_standing_context(self.user)
        p = result["personalization"]
        self.assertTrue(p["cos_name"])  # default 'Chief of Staff' or custom
        self.assertEqual(p["enabled_modules"], ["faith", "health"])  # finance False

    def test_current_screen_passthrough(self):
        screen = {"module": "health", "page_title": "Weight"}
        with mock.patch(_CACHE_FN, return_value=_fake_context()):
            result = get_standing_context(self.user, page_context=screen)
        self.assertEqual(result["current_screen"], screen)

    # --- output contract --------------------------------------------------
    def test_output_is_json_serializable(self):
        with mock.patch(_CACHE_FN, return_value=_fake_context()):
            result = get_standing_context(self.user)
        json.dumps(result)  # must not raise

    def test_pending_output_is_json_serializable(self):
        with mock.patch(_CACHE_FN, return_value=None):
            result = get_standing_context(self.user)
        json.dumps(result)

    def test_list_fields_are_capped(self):
        ctx = _fake_context()
        ctx["user_priorities"] = [f"p{i}" for i in range(20)]
        ctx["top_signals"] = [{"type": f"s{i}"} for i in range(20)]
        with mock.patch(_CACHE_FN, return_value=ctx):
            result = get_standing_context(self.user)
        self.assertLessEqual(len(result["priorities"]), 6)
        self.assertLessEqual(len(result["top_signals"]), 8)


class ExecutiveProjectionRefactorTests(TestCase):
    """The extracted build_executive_from_context must be a pure projection."""

    def test_pure_projection_returns_executive_keys(self):
        from apps.core.ai_orchestrator.cos_context import (
            build_executive_from_context,
        )
        executive = build_executive_from_context(_fake_context())
        for key in (
            "strategic_state_summary", "risk_flags", "momentum_indicators",
            "health_status", "recommended_focus_for_today", "tone_mode",
        ):
            self.assertIn(key, executive)
        # deterministic over input (no rebuild, no randomness)
        again = build_executive_from_context(_fake_context())
        self.assertEqual(executive["strategic_state_summary"],
                         again["strategic_state_summary"])
