"""
Phase 5A — ECC Pipeline Integration Tests.

Verifies that ECC is invoked from the personal_assistant pipeline
(not just unit-tested in isolation).

Tests:
1) "I'll finish the compensation model." → tightening question short-circuit
2) Input with time but missing done-definition → "What does 'done' mean..."
3) Input with time + done-definition → commitment confirmation
"""

from datetime import datetime
from unittest.mock import patch, MagicMock, PropertyMock

from django.test import TestCase
from django.utils import timezone

from apps.users.models import User


class _PipelineTestMixin:
    """Shared setup for ECC pipeline integration tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='ecc-pipeline@test.com', password='testpass123'
        )
        # Enable PA
        self.user.preferences.personal_assistant_enabled = True
        self.user.preferences.ai_enabled = True
        self.user.preferences.ai_data_consent = True
        self.user.preferences.ai_data_consent_date = timezone.now()
        self.user.preferences.personal_assistant_enabled = True
        self.user.preferences.personal_assistant_consent = True
        self.user.preferences.personal_assistant_consent_date = timezone.now()
        self.user.preferences.save()

    def _build_pa(self):
        """Build a PersonalAssistant instance for self.user."""
        from apps.ai.personal_assistant import PersonalAssistant
        return PersonalAssistant(self.user)

    def _mock_cos_context(self):
        """Return a minimal cos_context dict that passes all guards."""
        return {
            '_user': self.user,
            'blueprint_state': {},
            'protected_tiers': [],
            'capacity_snapshot': {},
            'drift_probability': {},
            'forecast_load_24h': 0,
            'forecast_load_72h': 0,
            'override_frequency_14d': 0,
            'persona_profile': {},
            'module_permissions': {
                'health': True, 'journal': True, 'faith': True,
                'life': True, 'purpose': True, 'finance': True,
                'capture': True, 'ai': True, 'personal_assistant': True,
            },
            'transformation_metrics': {},
            'active_fast_status': {},
            'medication_adherence_state': {},
            'alignment_score': 100,
            'drift_score': 0,
            'risk_warnings': [],
            'today_blocks_summary': [],
            'calendar_events_today': [],
            'trajectory_signals': {
                'renegotiation_patterns': [],
                'tier1_skip_patterns': [],
                'consecutive_tier1_skips': 0,
            },
        }


class ECCTighteningShortCircuitTest(_PipelineTestMixin, TestCase):
    """
    Test 1: "I'll finish the compensation model."
    Expected: ECC detects commitment, missing time → returns tightening question.
    No LLM call. No motivational text.
    """

    @patch('apps.ai.personal_assistant.ai_service')
    @patch('apps.core.ai_orchestrator.cos_context.build_cos_context')
    @patch('apps.core.ai_orchestrator.cos_context._build_trajectory_signals')
    @patch('apps.core.blueprint.learning_mode.is_learning_mode_active',
           return_value=False)
    def test_missing_time_short_circuits(
        self, mock_lm, mock_traj, mock_build_cos, mock_ai
    ):
        mock_ai.is_available = True
        mock_ai._call_api = MagicMock(
            return_value="This should NOT be returned"
        )
        mock_build_cos.return_value = self._mock_cos_context()
        mock_traj.return_value = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        pa = self._build_pa()
        conversation = pa.get_or_create_conversation()

        # Call _generate_response directly — this is where ECC lives
        response = pa._generate_response(
            "I'll finish the compensation model.",
            conversation,
        )

        # ECC should short-circuit with tightening question
        self.assertEqual(
            response,
            "When specifically will this be completed?"
        )

        # LLM should NOT have been called
        mock_ai._call_api.assert_not_called()


class ECCMissingDoneDefinitionTest(_PipelineTestMixin, TestCase):
    """
    Test 2: Input with explicit time but missing done-definition.
    Expected: "What does 'done' mean in one sentence?"
    """

    @patch('apps.ai.personal_assistant.ai_service')
    @patch('apps.core.ai_orchestrator.cos_context.build_cos_context')
    @patch('apps.core.ai_orchestrator.cos_context._build_trajectory_signals')
    @patch('apps.core.blueprint.learning_mode.is_learning_mode_active',
           return_value=False)
    def test_missing_done_definition_short_circuits(
        self, mock_lm, mock_traj, mock_build_cos, mock_ai
    ):
        mock_ai.is_available = True
        mock_ai._call_api = MagicMock(
            return_value="This should NOT be returned"
        )
        mock_build_cos.return_value = self._mock_cos_context()
        mock_traj.return_value = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        pa = self._build_pa()
        conversation = pa.get_or_create_conversation()

        response = pa._generate_response(
            "I'll finish the compensation model by 5pm today",
            conversation,
        )

        self.assertEqual(
            response,
            "What does 'done' mean in one sentence?"
        )
        mock_ai._call_api.assert_not_called()


class ECCCommitmentConfirmationTest(_PipelineTestMixin, TestCase):
    """
    Test 3: Input with explicit time AND done-definition.
    Expected: Commitment confirmation in exact format.
    """

    @patch('apps.ai.personal_assistant.ai_service')
    @patch('apps.core.ai_orchestrator.cos_context.build_cos_context')
    @patch('apps.core.ai_orchestrator.cos_context._build_trajectory_signals')
    @patch('apps.core.blueprint.learning_mode.is_learning_mode_active',
           return_value=False)
    def test_full_commitment_returns_confirmation(
        self, mock_lm, mock_traj, mock_build_cos, mock_ai
    ):
        mock_ai.is_available = True
        mock_ai._call_api = MagicMock(return_value="LLM response")
        mock_build_cos.return_value = self._mock_cos_context()
        mock_traj.return_value = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        pa = self._build_pa()
        conversation = pa.get_or_create_conversation()

        response = pa._generate_response(
            "I'll finish the compensation model by 5pm today. "
            "Done means the model spreadsheet is submitted to my manager.",
            conversation,
        )

        # Should contain exact confirmation format
        self.assertIn('Commitment set:', response)
        self.assertIn('Done means:', response)

        # This is a short-circuit (confirmation returned), no LLM call
        mock_ai._call_api.assert_not_called()


class ECCNoCommitmentPassthroughTest(_PipelineTestMixin, TestCase):
    """
    Non-commitment input should pass through to normal LLM pipeline.
    """

    @patch('apps.ai.personal_assistant.ai_service')
    @patch('apps.ai.personal_assistant.process_assistant_message')
    @patch('apps.ai.web_search_service.needs_web_search', return_value=False)
    @patch('apps.core.ai_orchestrator.cos_context.build_cos_context')
    @patch('apps.core.ai_orchestrator.cos_context._build_trajectory_signals')
    @patch('apps.core.blueprint.learning_mode.is_learning_mode_active',
           return_value=False)
    def test_non_commitment_reaches_llm(
        self, mock_lm, mock_traj, mock_build_cos, mock_web,
        mock_pam, mock_ai
    ):
        mock_ai.is_available = True
        mock_ai._call_api = MagicMock(return_value="Normal LLM response")
        mock_build_cos.return_value = self._mock_cos_context()
        mock_traj.return_value = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }
        # Mock personal data query to not intercept
        mock_pam.return_value = {
            'is_personal_query': False,
            'has_data': False,
            'system_prompt': '',
        }

        pa = self._build_pa()
        conversation = pa.get_or_create_conversation()

        response = pa._generate_response(
            "Tell me something interesting about productivity.",
            conversation,
        )

        # Non-commitment → should reach LLM
        mock_ai._call_api.assert_called_once()


class ECCProcessECCDetectionCalledTest(_PipelineTestMixin, TestCase):
    """
    Verify process_ecc_detection is actually called from the pipeline.
    """

    @patch('apps.ai.personal_assistant.ai_service')
    @patch('apps.core.ai_orchestrator.commitment_contract.process_ecc_detection')
    @patch('apps.core.ai_orchestrator.cos_context.build_cos_context')
    @patch('apps.core.ai_orchestrator.cos_context._build_trajectory_signals')
    @patch('apps.core.blueprint.learning_mode.is_learning_mode_active',
           return_value=False)
    def test_process_ecc_detection_called(
        self, mock_lm, mock_traj, mock_build_cos, mock_ecc, mock_ai
    ):
        mock_ai.is_available = True
        mock_ai._call_api = MagicMock(return_value="LLM response")
        mock_build_cos.return_value = self._mock_cos_context()
        mock_traj.return_value = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }
        # ECC returns None (no commitment detected) — passthrough
        mock_ecc.return_value = None

        pa = self._build_pa()
        conversation = pa.get_or_create_conversation()

        pa._generate_response(
            "I'll finish the compensation model.",
            conversation,
        )

        # process_ecc_detection MUST have been called
        mock_ecc.assert_called_once()
        call_kwargs = mock_ecc.call_args
        # Verify the user message was passed
        self.assertIn(
            "I'll finish the compensation model.",
            str(call_kwargs),
        )
