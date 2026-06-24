# ==============================================================================
# File: apps/ai/tests/test_cos_gateway.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Phase 0A — gateway behavior + legacy quarantine + import drift
# ==============================================================================
"""
Proves the Single Interactive Conversational Gateway:
  * resolves runtime ownership once (CoS for flag-ON, legacy for flag-OFF);
  * returns a standard CoSResponse envelope;
  * QUARANTINE: a flag-ON user executes ZERO legacy conversational components
    across every migrated interactive surface (tripwires fail on execution);
  * IMPORT DRIFT: no module under apps/ai/chatgpt_cos/ imports a forbidden
    legacy conversational module.
"""

import ast
import contextlib
import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai.cos_gateway import (
    CoSGateway,
    CoSResponse,
    SURFACE_CHAT,
    SURFACE_CHAT_STREAM,
)

User = get_user_model()

_LLM = "apps.ai.services.ai_service._call_api_with_tools"

# Every forbidden legacy conversational symbol (dotted target for mock.patch).
FORBIDDEN_TARGETS = [
    "apps.ai.deterministic_router.classify_and_route",
    "apps.ai.response_governor.resolve_response_type",
    "apps.ai.cos_mode_router.resolve_cos_mode",
    "apps.ai.affirmation_detector.handle_affirmed_completion",
    "apps.ai.confirmation_detector.handle_proactive_confirmation",
    "apps.ai.cos_truth_validator.validate_locked_facts",
    "apps.ai.cos_truth_validator.validate_response_truth",
    "apps.ai.narration_contract_validator.validate_narration_contract",
    "apps.ai.beth_checkin_renderer.build_cos_structured_output",
    "apps.ai.beth_checkin_renderer.render_checkin_for_time",
    "apps.ai.proactive_checkins.ProactiveCheckInService",
    "apps.ai.assistant_intelligence.IntelligentCheckInService",
    "apps.ai.personal_assistant.PersonalAssistant.send_message",
    "apps.ai.personal_assistant.PersonalAssistant.send_message_stream",
    "apps.ai.personal_assistant.PersonalAssistant._generate_response",
    "apps.ai.personal_assistant.PersonalAssistant._generate_response_stream",
    "apps.core.cos.prompt_builder.build_personal_assistant_prompt",
]

# Forbidden module imports for the import-drift guard.
FORBIDDEN_MODULES = {
    "apps.ai.deterministic_router",
    "apps.ai.response_governor",
    "apps.ai.cos_mode_router",
    "apps.ai.affirmation_detector",
    "apps.ai.confirmation_detector",
    "apps.ai.cos_truth_validator",
    "apps.ai.narration_contract_validator",
    "apps.ai.beth_checkin_renderer",
    "apps.ai.proactive_checkins",
    "apps.ai.assistant_intelligence",
    "apps.ai.personal_assistant",
    "apps.ai.greeting_service",
    "apps.ai.state_assessment",
    "apps.ai.priority_generator",
    "apps.core.cos.prompt_builder",
}


class QuarantineBreach(AssertionError):
    """Raised when a flag-ON conversation touches a legacy conversational symbol."""


@contextlib.contextmanager
def tripwires(targets):
    """Patch each target so executing it raises QuarantineBreach. Missing
    symbols are skipped (build-tolerant)."""
    patchers = []
    armed = []
    for tgt in targets:
        def _trip(*a, _n=tgt, **k):
            raise QuarantineBreach(f"Legacy conversational component executed: {_n}")
        try:
            p = mock.patch(tgt, side_effect=_trip)
            p.start()
        except (AttributeError, ImportError, ModuleNotFoundError):
            continue
        patchers.append(p)
        armed.append(tgt)
    try:
        yield armed
    finally:
        for p in patchers:
            p.stop()


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class GatewayRoutingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cos_user = User.objects.create_user(email="g_cos@example.com", password="x")
        cls.cos_user.preferences.use_chatgpt_cos = True
        cls.cos_user.preferences.save()
        cls.legacy_user = User.objects.create_user(email="g_leg@example.com", password="x")
        cls.legacy_user.preferences.use_chatgpt_cos = False
        cls.legacy_user.preferences.save()

    def test_resolve_runtime_flag_on_is_chatgpt(self):
        rt = CoSGateway.resolve_runtime(self.cos_user)
        self.assertEqual(rt.name, "chatgpt_cos")

    def test_resolve_runtime_flag_off_is_legacy(self):
        rt = CoSGateway.resolve_runtime(self.legacy_user)
        self.assertEqual(rt.name, "legacy_beth")

    def test_unmigrated_surface_rejected(self):
        with self.assertRaises(ValueError):
            CoSGateway.respond(user=self.cos_user, surface="weekly_analysis",
                               message="x")

    def test_flag_on_returns_standard_envelope(self):
        with mock.patch(_LLM, return_value="You are doing well."):
            env = CoSGateway.respond(user=self.cos_user, surface=SURFACE_CHAT,
                                     message="how am I?")
        self.assertIsInstance(env, CoSResponse)
        self.assertEqual(env.runtime, "chatgpt_cos")
        self.assertEqual(env.surface, SURFACE_CHAT)
        self.assertEqual(env.envelope_version, 1)
        self.assertTrue(env.text)
        self.assertIn("conversation_id", env.meta)


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class GatewayQuarantineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cos_user = User.objects.create_user(email="q_cos@example.com", password="x")
        cls.cos_user.preferences.use_chatgpt_cos = True
        cls.cos_user.preferences.save()
        cls.legacy_user = User.objects.create_user(email="q_leg@example.com", password="x")
        cls.legacy_user.preferences.use_chatgpt_cos = False
        cls.legacy_user.preferences.save()

    def test_flag_on_chat_executes_zero_legacy(self):
        with tripwires(FORBIDDEN_TARGETS), mock.patch(_LLM, return_value="ok"):
            env = CoSGateway.respond(user=self.cos_user, surface=SURFACE_CHAT,
                                     message="what is my weight?")
        self.assertEqual(env.runtime, "chatgpt_cos")
        self.assertTrue(env.text)

    def test_flag_on_stream_executes_zero_legacy(self):
        with tripwires(FORBIDDEN_TARGETS), mock.patch(_LLM, return_value="ok"):
            env = CoSGateway.respond(user=self.cos_user, surface=SURFACE_CHAT_STREAM,
                                     message="how am I?", stream=True)
        self.assertEqual(env.runtime, "chatgpt_cos")
        self.assertIsNotNone(env.stream_job_id)

    def test_flag_off_routes_to_legacy(self):
        # Positive control: legacy runtime SHOULD reach a quarantined symbol,
        # proving the gateway routes flag-OFF users to legacy Beth.
        with self.assertRaises(QuarantineBreach):
            with tripwires(["apps.ai.personal_assistant.PersonalAssistant.send_message"]):
                CoSGateway.respond(user=self.legacy_user, surface=SURFACE_CHAT,
                                   message="hi")


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class StructuredSuppressionTests(TestCase):
    """Phase 0A.2 — gateway-owned narrative suppression mechanism."""

    @classmethod
    def setUpTestData(cls):
        cls.cos = User.objects.create_user(email="s_cos@example.com", password="x")
        cls.cos.preferences.use_chatgpt_cos = True
        cls.cos.preferences.save()
        cls.legacy = User.objects.create_user(email="s_leg@example.com", password="x")
        cls.legacy.preferences.use_chatgpt_cos = False
        cls.legacy.preferences.save()

    def test_structured_suppresses_cos_without_calling_legacy(self):
        called = []
        out = CoSGateway.structured(
            user=self.cos, surface="weekly_analysis",
            legacy=lambda: called.append("LEGACY") or {"x": 1},
            suppressed=lambda reason: {"suppressed": True, "reason": reason},
        )
        self.assertEqual(called, [])            # legacy producer NEVER called
        self.assertTrue(out["suppressed"])
        self.assertIn("suppressed", out["reason"])

    def test_structured_runs_legacy_for_flag_off(self):
        called = []
        out = CoSGateway.structured(
            user=self.legacy, surface="weekly_analysis",
            legacy=lambda: (called.append("LEGACY"), {"ok": True})[1],
            suppressed=lambda reason: {"suppressed": True},
        )
        self.assertEqual(called, ["LEGACY"])
        self.assertEqual(out, {"ok": True})

    def test_narrative_suppressed_for_cos(self):
        called = []
        nar = CoSGateway.narrative(
            user=self.cos, surface="quick_reply",
            legacy_producer=lambda: called.append("X") or "Great!",
        )
        self.assertEqual(called, [])
        self.assertTrue(nar.suppressed)
        self.assertEqual(nar.text, "")
        self.assertTrue(nar.suppressed_reason)

    def test_narrative_legacy_text_for_flag_off(self):
        nar = CoSGateway.narrative(
            user=self.legacy, surface="quick_reply",
            legacy_producer=lambda: "Great!",
        )
        self.assertFalse(nar.suppressed)
        self.assertEqual(nar.text, "Great!")


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class NarrativeSurfaceEndpointTests(TestCase):
    """Phase 0A.2 — every migrated interactive surface, end to end: a flag-ON
    user gets a SUPPRESSED response and ZERO legacy conversational code runs."""

    @classmethod
    def setUpTestData(cls):
        from django.conf import settings as dj_settings
        from apps.users.models import TermsAcceptance
        cls.user = User.objects.create_user(email="ep_cos@example.com", password="x")
        TermsAcceptance.objects.create(
            user=cls.user,
            terms_version=dj_settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        p = cls.user.preferences
        p.has_completed_onboarding = True
        p.ai_enabled = True
        p.ai_data_consent = True
        p.personal_assistant_enabled = True
        p.personal_assistant_consent = True
        p.use_chatgpt_cos = True
        p.save()

    def setUp(self):
        self.client.force_login(self.user)

    def test_get_surfaces_suppressed_no_legacy(self):
        from django.urls import reverse
        surfaces = [
            "ai:api_state", "ai:api_weekly_analysis", "ai:api_monthly_analysis",
            "ai:api_opening", "ai:api_drift", "ai:api_goal_progress",
            "ai:api_reflection", "ai:api_priorities",
        ]
        with tripwires(FORBIDDEN_TARGETS):
            for name in surfaces:
                resp = self.client.get(reverse(name))
                self.assertEqual(resp.status_code, 200, name)
                self.assertIn("suppressed_reason", resp.json(), name)

    def test_post_surfaces_suppressed_no_legacy(self):
        from django.urls import reverse
        with tripwires(FORBIDDEN_TARGETS):
            r1 = self.client.post(reverse("ai:api_session_start"), data="{}",
                                  content_type="application/json")
            self.assertEqual(r1.status_code, 200)
            self.assertEqual(r1.json().get("action"), "none")
            self.assertIn("suppressed_reason", r1.json())

            r2 = self.client.post(reverse("ai:api_briefing"), data="{}",
                                  content_type="application/json")
            self.assertEqual(r2.status_code, 200)
            self.assertIn("suppressed_reason", r2.json())


class ImportDriftTests(TestCase):
    def test_chatgpt_cos_package_imports_no_legacy_conversation(self):
        import apps.ai.chatgpt_cos as pkg
        pkg_dir = os.path.dirname(pkg.__file__)
        violations = []
        for root, _dirs, files in os.walk(pkg_dir):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                path = os.path.join(root, fname)
                with open(path, "r", encoding="utf-8") as fh:
                    tree = ast.parse(fh.read(), filename=path)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        if node.module in FORBIDDEN_MODULES:
                            violations.append(f"{fname}: from {node.module}")
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name in FORBIDDEN_MODULES:
                                violations.append(f"{fname}: import {alias.name}")
        self.assertEqual(violations, [], f"clean runtime imports legacy: {violations}")
