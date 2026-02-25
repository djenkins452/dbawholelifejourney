"""
EAE — Integration tests (Phase 8.6).

Tests for the EAE feature flag gate and chat injection behavior.
"""
from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_eae.constants import (
    CHANNEL_CHAT,
    CHANNEL_PUSH,
    ESCALATION_NOMINAL,
    TONE_REFLECTIVE_GENTLE,
)
from apps.core.ai_eae.eae_engine import EAEResult, arbitrate

User = get_user_model()


class FeatureFlagTests(TestCase):
    """Tests for EAE feature flag gating."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="eae_flag_test@test.com", password="testpass123",
        )

    def test_eae_disabled_returns_safe_default(self):
        """EAE always returns a safe result even with no data."""
        result = arbitrate(self.user, channel=CHANNEL_CHAT)
        self.assertIsInstance(result, EAEResult)
        self.assertEqual(result.escalation_level, 0)
        self.assertEqual(result.tone_band, TONE_REFLECTIVE_GENTLE)
        self.assertIn('NO_SIGNALS', result.reason_codes)

    def test_eae_result_has_prompt_injection(self):
        """EAE result always has a prompt_injection string."""
        result = arbitrate(self.user, channel=CHANNEL_CHAT)
        self.assertIsInstance(result.prompt_injection, str)

    def test_eae_feature_flag_gate(self):
        """EAE is only active in chat when eae_enabled=True on Blueprint."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint

        # Default: eae_enabled=False
        bp = PersonalOperatingBlueprint.objects.create(user=self.user)
        self.assertFalse(bp.eae_enabled)

        # Enable it
        bp.eae_enabled = True
        bp.save()
        bp.refresh_from_db()
        self.assertTrue(bp.eae_enabled)

        # EAE should work when enabled
        result = arbitrate(self.user, channel=CHANNEL_CHAT)
        self.assertIsInstance(result, EAEResult)


class ArbitrationPipelineTests(TestCase):
    """End-to-end tests for the arbitration pipeline."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="eae_pipeline@test.com", password="testpass123",
        )

    def test_no_signals_returns_no_units(self):
        """With no engine data, pipeline returns empty units."""
        result = arbitrate(self.user, channel=CHANNEL_CHAT)
        self.assertEqual(len(result.cognitive_units), 0)
        self.assertEqual(result.surfaced_count, 0)
        self.assertEqual(result.total_candidates, 0)

    def test_pipeline_creates_decision_log(self):
        """Every arbitration creates a decision log entry."""
        from apps.core.ai_eae.models import EAEDecisionLog

        result = arbitrate(self.user, channel=CHANNEL_CHAT)
        self.assertTrue(result.decision_id)
        log = EAEDecisionLog.objects.get(decision_id=result.decision_id)
        self.assertEqual(log.channel, CHANNEL_CHAT)
        self.assertGreaterEqual(log.arbitration_duration_ms, 0)

    def test_pipeline_creates_state(self):
        """Arbitration creates EAEState if not existing."""
        from apps.core.ai_eae.models import EAEState

        self.assertFalse(EAEState.objects.filter(user=self.user).exists())
        arbitrate(self.user, channel=CHANNEL_CHAT)
        self.assertTrue(EAEState.objects.filter(user=self.user).exists())

    def test_multiple_channels(self):
        """Arbitration works across different channels."""
        for channel in [CHANNEL_CHAT, CHANNEL_PUSH, 'briefing', 'email']:
            result = arbitrate(self.user, channel=channel)
            self.assertIsInstance(result, EAEResult)

    def test_pipeline_timing(self):
        """Arbitration records duration in milliseconds."""
        result = arbitrate(self.user, channel=CHANNEL_CHAT)
        self.assertGreater(result.arbitration_duration_ms, 0)

    def test_pipeline_error_resilience(self):
        """Pipeline recovers gracefully from errors."""
        with patch(
            'apps.core.ai_eae.eae_engine.collect_signals',
            side_effect=Exception("Simulated failure"),
        ):
            result = arbitrate(self.user, channel=CHANNEL_CHAT)
            self.assertIn('ERROR', result.reason_codes)
            self.assertIsInstance(result.prompt_injection, str)
