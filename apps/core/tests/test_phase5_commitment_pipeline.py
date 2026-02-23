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

from apps.ai.models import AssistantMessage
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


class ECCPrecedenceOverTaskCreationTest(_PipelineTestMixin, TestCase):
    """
    ECC must block task creation when tightening is needed.

    Input: "I'll finish the compensation model by Friday at 3 PM."
    Expected: "What does 'done' mean in one sentence?"
    Must NOT call intent_service.recognize_intents or any task creation.
    """

    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    def test_ecc_blocks_task_creation_with_tightening(
        self, mock_ai, mock_ai_cls
    ):
        mock_ai.is_available = True
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)

        pa = self._build_pa()
        conversation = pa.get_or_create_conversation()

        # Mock intent_service to track if it's called
        from apps.ai import intent_service as intent_mod
        original_recognize = intent_mod.intent_service.recognize_intents

        recognize_called = {'called': False}

        def track_recognize(*args, **kwargs):
            recognize_called['called'] = True
            return original_recognize(*args, **kwargs)

        with patch.object(
            intent_mod.intent_service, 'recognize_intents',
            side_effect=track_recognize
        ):
            result = pa.send_message(
                "I'll finish the compensation model by Friday at 3 PM.",
                conversation=conversation,
            )

        # ECC should short-circuit with done-definition question
        self.assertEqual(
            result['response'],
            "What does 'done' mean in one sentence?"
        )

        # Intent recognition should NOT have been called
        self.assertFalse(
            recognize_called['called'],
            "Intent recognition should not run when ECC tightening is active"
        )

    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    def test_ecc_blocks_task_creation_missing_time(
        self, mock_ai, mock_ai_cls
    ):
        """Commitment without time → tightening before any task logic."""
        mock_ai.is_available = True
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)

        pa = self._build_pa()
        conversation = pa.get_or_create_conversation()

        from apps.ai import intent_service as intent_mod
        recognize_called = {'called': False}

        def track_recognize(*args, **kwargs):
            recognize_called['called'] = True
            return []

        with patch.object(
            intent_mod.intent_service, 'recognize_intents',
            side_effect=track_recognize
        ):
            result = pa.send_message(
                "I'll finish the compensation model.",
                conversation=conversation,
            )

        self.assertEqual(
            result['response'],
            "When specifically will this be completed?"
        )
        self.assertFalse(
            recognize_called['called'],
            "Intent recognition should not run when ECC tightening is active"
        )


class ECCCrossMessageContinuityTest(_PipelineTestMixin, TestCase):
    """
    Phase 5B: Active commitments must persist across messages via
    conversation.metadata, not ephemeral instance attributes.
    """

    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    def test_commitment_persists_across_messages(
        self, mock_ai, mock_ai_cls
    ):
        """
        Message 1: Create full commitment → stored in metadata.
        Message 2: Renegotiation → commitment loaded from metadata.
        """
        mock_ai.is_available = True
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)

        # --- Message 1: Full commitment ---
        pa1 = self._build_pa()
        conversation = pa1.get_or_create_conversation()
        result1 = pa1.send_message(
            "I'll finish the compensation model by 5pm today. "
            "Done means the model spreadsheet is submitted to my manager.",
            conversation=conversation,
        )
        self.assertIn('Commitment set:', result1['response'])

        # Verify commitment stored in metadata
        conversation.refresh_from_db()
        ecc_data = conversation.metadata.get('ecc_active_commitment')
        self.assertIsNotNone(
            ecc_data, "Commitment must be stored in conversation.metadata"
        )
        self.assertEqual(ecc_data['status'], 'pending')

        # --- Message 2: Renegotiation (new PA instance = new request) ---
        pa2 = self._build_pa()
        result2 = pa2.send_message(
            "Move it to next week instead.",
            conversation=conversation,
        )
        # Renegotiation should fire, not "no commitment detected"
        self.assertIsNotNone(result2)
        # Should NOT get a tightening question for new commitment
        self.assertNotEqual(
            result2['response'],
            "When specifically will this be completed?",
        )

    @patch('apps.core.ai_orchestrator.cos_context.determine_activation_state')
    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    def test_renegotiation_early_erosion_blocks_across_messages(
        self, mock_ai, mock_ai_cls, mock_determine_tier
    ):
        """
        EARLY_EROSION tier: renegotiation on persisted commitment
        produces A/B blocking choices via real tier computation.
        """
        mock_ai.is_available = True
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)

        # --- Message 1: Create commitment (CLEAN tier) ---
        mock_determine_tier.return_value = 'CLEAN'
        pa1 = self._build_pa()
        conversation = pa1.get_or_create_conversation()
        result1 = pa1.send_message(
            "I'll finish the report by 5pm today. "
            "Done means the report is reviewed and submitted.",
            conversation=conversation,
        )
        self.assertIn('Commitment set:', result1['response'])

        # --- Message 2: Renegotiation with EARLY_EROSION tier ---
        mock_determine_tier.return_value = 'EARLY_EROSION'
        pa2 = self._build_pa()
        result2 = pa2.send_message(
            "I'm going to move it to next week instead.",
            conversation=conversation,
        )
        # Should get A/B blocking choices
        self.assertIn('A)', result2['response'])
        self.assertIn('B)', result2['response'])

    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    def test_commitment_serialization_roundtrip(
        self, mock_ai, mock_ai_cls
    ):
        """Commitment survives JSON serialization in metadata."""
        from apps.core.ai_orchestrator.commitment_contract import Commitment

        mock_ai.is_available = True
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)

        # Create commitment via pipeline
        pa = self._build_pa()
        conversation = pa.get_or_create_conversation()
        pa.send_message(
            "I will decide on the vendor by tomorrow. "
            "Done means the contract is signed.",
            conversation=conversation,
        )

        # Reload from DB and deserialize
        conversation.refresh_from_db()
        ecc_data = conversation.metadata.get('ecc_active_commitment')
        self.assertIsNotNone(ecc_data)

        restored = Commitment.from_dict(ecc_data)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.status, 'pending')
        self.assertEqual(restored.commitment_type, 'DECIDE')
        self.assertIn('vendor', restored.normalized_text.lower())

    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    def test_extract_commitment_fields_not_called_on_renegotiation(
        self, mock_ai, mock_ai_cls
    ):
        """
        When renegotiating a persisted commitment,
        extract_commitment_fields must NOT be called.
        """
        mock_ai.is_available = True
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)

        # Create commitment
        pa1 = self._build_pa()
        conversation = pa1.get_or_create_conversation()
        pa1.send_message(
            "I'll finish the report by 5pm today. "
            "Done means the report is submitted.",
            conversation=conversation,
        )

        # Renegotiate with mock on extract
        pa2 = self._build_pa()
        with patch(
            'apps.core.ai_orchestrator.commitment_contract'
            '.extract_commitment_fields'
        ) as mock_extract:
            pa2.send_message(
                "Push it to tomorrow instead.",
                conversation=conversation,
            )
            mock_extract.assert_not_called()


class ECCTierUnificationTest(_PipelineTestMixin, TestCase):
    """
    Phase 5B: send_message() must compute tier via
    determine_activation_state(), not default to CLEAN.
    """

    @patch('apps.core.ai_orchestrator.cos_context.determine_activation_state')
    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    def test_send_message_uses_real_tier_for_blocking(
        self, mock_ai, mock_ai_cls, mock_determine_tier
    ):
        """
        Force EARLY_EROSION via mock → send commitment → renegotiate
        → verify blocked A/B output via send_message() path.
        """
        mock_ai.is_available = True
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)

        # Message 1: Create commitment (CLEAN tier allows it)
        mock_determine_tier.return_value = 'CLEAN'
        pa1 = self._build_pa()
        conversation = pa1.get_or_create_conversation()
        result1 = pa1.send_message(
            "I'll finish the report by 5pm today. "
            "Done means the report is reviewed and submitted.",
            conversation=conversation,
        )
        self.assertIn('Commitment set:', result1['response'])

        # Message 2: Renegotiation under EARLY_EROSION
        mock_determine_tier.return_value = 'EARLY_EROSION'
        pa2 = self._build_pa()
        result2 = pa2.send_message(
            "I'm going to move it to next week instead.",
            conversation=conversation,
        )
        # Must get blocked A/B choices, not CLEAN renegotiation
        self.assertIn('A)', result2['response'])
        self.assertIn('B)', result2['response'])
        self.assertIn(
            'Keep original commitment',
            result2['response'],
        )
        self.assertIn(
            'Formally cancel and accept consequence',
            result2['response'],
        )

    @patch('apps.core.ai_orchestrator.cos_context.determine_activation_state')
    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    def test_send_message_does_not_default_to_clean(
        self, mock_ai, mock_ai_cls, mock_determine_tier
    ):
        """
        Verify send_message() calls determine_activation_state(),
        not getattr(self, '_ecc_last_tier', 'CLEAN').
        """
        mock_ai.is_available = True
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)
        mock_determine_tier.return_value = 'STRUCTURAL_DRIFT'

        pa = self._build_pa()
        conversation = pa.get_or_create_conversation()

        # Create commitment first (needs CLEAN to form)
        mock_determine_tier.return_value = 'CLEAN'
        pa.send_message(
            "I'll finish the report by 5pm today. "
            "Done means the report is submitted.",
            conversation=conversation,
        )

        # Now try renegotiation under STRUCTURAL_DRIFT
        mock_determine_tier.return_value = 'STRUCTURAL_DRIFT'
        pa2 = self._build_pa()
        result = pa2.send_message(
            "Push it to next week.",
            conversation=conversation,
        )
        # STRUCTURAL_DRIFT must block renegotiation
        self.assertIn('A)', result['response'])
        self.assertIn('B)', result['response'])
        # determine_activation_state must have been called
        self.assertTrue(mock_determine_tier.called)

    @patch('apps.core.ai_orchestrator.cos_context.determine_activation_state')
    @patch('apps.core.ai_orchestrator.cos_context.build_cos_context')
    @patch('apps.core.ai_orchestrator.cos_context._build_trajectory_signals')
    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    @patch('apps.core.blueprint.learning_mode.is_learning_mode_active',
           return_value=False)
    def test_send_message_and_generate_response_same_tier(
        self, mock_lm, mock_ai, mock_ai_cls,
        mock_traj, mock_build_cos, mock_determine_tier
    ):
        """
        Both paths must produce identical tier for the same input.
        """
        mock_ai.is_available = True
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)
        mock_determine_tier.return_value = 'EARLY_EROSION'
        mock_build_cos.return_value = self._mock_cos_context()
        mock_traj.return_value = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        pa = self._build_pa()
        conversation = pa.get_or_create_conversation()

        # Create commitment via send_message (CLEAN for creation)
        mock_determine_tier.return_value = 'CLEAN'
        pa.send_message(
            "I'll finish the report by 5pm today. "
            "Done means the report is submitted.",
            conversation=conversation,
        )

        # Renegotiate — both paths should see EARLY_EROSION
        mock_determine_tier.return_value = 'EARLY_EROSION'

        # Test via send_message()
        pa2 = self._build_pa()
        result_sm = pa2.send_message(
            "Move it to next week.",
            conversation=conversation,
        )

        # Reset commitment for second test
        conversation.refresh_from_db()
        conversation.metadata['ecc_active_commitment']['status'] = 'pending'
        conversation.save(update_fields=['metadata'])

        # Test via _generate_response()
        pa3 = self._build_pa()
        result_gr = pa3._generate_response(
            "Move it to next week.",
            conversation,
        )

        # Both must produce blocking response
        self.assertIn('A)', result_sm['response'])
        self.assertIn('B)', result_sm['response'])
        self.assertIn('A)', result_gr)
        self.assertIn('B)', result_gr)


class ECCClosurePrecedenceTest(_PipelineTestMixin, TestCase):
    """
    Phase 5C: 'It's done.' must close the active commitment
    before any intent recognition or task creation runs.
    """

    @patch('apps.core.ai_orchestrator.cos_context.determine_activation_state',
           return_value='CLEAN')
    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    def test_closure_before_intent_recognition(
        self, mock_ai, mock_ai_cls, mock_determine_tier
    ):
        """
        1) Create commitment
        2) Separate request: 'It's done.'
        3) Verify: closure executed, metadata cleared, lock-in returned,
           intent recognition NOT called.
        """
        mock_ai.is_available = True
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)

        # --- Message 1: Create commitment ---
        pa1 = self._build_pa()
        conversation = pa1.get_or_create_conversation()
        result1 = pa1.send_message(
            "I'll finish the report by 5pm today. "
            "Done means the report is reviewed and submitted.",
            conversation=conversation,
        )
        self.assertIn('Commitment set:', result1['response'])

        # Verify commitment stored
        conversation.refresh_from_db()
        self.assertIsNotNone(
            conversation.metadata.get('ecc_active_commitment')
        )

        # --- Message 2: Close commitment (new PA instance = new request) ---
        pa2 = self._build_pa()

        from apps.ai import intent_service as intent_mod
        recognize_called = {'called': False}

        def track_recognize(*args, **kwargs):
            recognize_called['called'] = True
            return []

        with patch.object(
            intent_mod.intent_service, 'recognize_intents',
            side_effect=track_recognize
        ):
            result2 = pa2.send_message(
                "It's done.",
                conversation=conversation,
            )

        # Positive lock-in response
        self.assertEqual(
            result2['response'],
            "Time boundary honored. Repeat this structure.",
        )

        # Commitment cleared from metadata
        conversation.refresh_from_db()
        self.assertIsNone(
            conversation.metadata.get('ecc_active_commitment'),
            "Commitment must be removed from metadata after closure",
        )

        # Intent recognition must NOT have been called
        self.assertFalse(
            recognize_called['called'],
            "Intent recognition should not run when ECC closure fires",
        )

    @patch('apps.core.ai_orchestrator.cos_context.determine_activation_state',
           return_value='CLEAN')
    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    def test_done_closes_commitment(
        self, mock_ai, mock_ai_cls, mock_determine_tier
    ):
        """'Done' (bare word) triggers closure."""
        mock_ai.is_available = True
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)

        pa1 = self._build_pa()
        conversation = pa1.get_or_create_conversation()
        pa1.send_message(
            "I'll finish the report by 5pm today. "
            "Done means the report is submitted.",
            conversation=conversation,
        )

        pa2 = self._build_pa()
        result = pa2.send_message(
            "Done",
            conversation=conversation,
        )
        self.assertEqual(
            result['response'],
            "Time boundary honored. Repeat this structure.",
        )
        conversation.refresh_from_db()
        self.assertIsNone(
            conversation.metadata.get('ecc_active_commitment'),
        )

    @patch('apps.core.ai_orchestrator.cos_context.determine_activation_state',
           return_value='CLEAN')
    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    def test_non_closure_does_not_close(
        self, mock_ai, mock_ai_cls, mock_determine_tier
    ):
        """Non-closure input does not close the commitment."""
        mock_ai.is_available = True
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)

        pa1 = self._build_pa()
        conversation = pa1.get_or_create_conversation()
        pa1.send_message(
            "I'll finish the report by 5pm today. "
            "Done means the report is submitted.",
            conversation=conversation,
        )

        # Renegotiation message should NOT close
        pa2 = self._build_pa()
        pa2.send_message(
            "Move it to tomorrow instead.",
            conversation=conversation,
        )
        conversation.refresh_from_db()
        # Commitment should still exist (renegotiated, not closed)
        ecc = conversation.metadata.get('ecc_active_commitment')
        self.assertIsNotNone(
            ecc,
            "Non-closure input must not remove commitment from metadata",
        )


class ECCClosureHardShortCircuitTest(_PipelineTestMixin, TestCase):
    """
    Phase 5C Hard Short-Circuit Enforcement.

    Closure must be a HARD RETURN: exactly one AssistantMessage,
    no intent recognition, no calibration recording, no rolling
    summary generation.
    """

    @patch('apps.core.ai_orchestrator.cos_context.determine_activation_state',
           return_value='CLEAN')
    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    def test_closure_creates_exactly_one_assistant_message(
        self, mock_ai, mock_ai_cls, mock_determine_tier
    ):
        """Closure must create exactly ONE AssistantMessage with exact text."""
        mock_ai.is_available = True
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)

        pa1 = self._build_pa()
        conversation = pa1.get_or_create_conversation()
        pa1.send_message(
            "I'll finish the report by 5pm today. "
            "Done means the report is submitted.",
            conversation=conversation,
        )

        # Count assistant messages before closure
        msgs_before = AssistantMessage.objects.filter(
            conversation=conversation, role='assistant',
        ).count()

        pa2 = self._build_pa()
        result = pa2.send_message(
            "It's done.",
            conversation=conversation,
        )

        # Exactly ONE new assistant-role AssistantMessage
        msgs_after = AssistantMessage.objects.filter(
            conversation=conversation, role='assistant',
        ).count()
        self.assertEqual(
            msgs_after - msgs_before, 1,
            "Closure must create exactly one assistant AssistantMessage",
        )

        # Content must be exact positive lock-in
        last_msg = AssistantMessage.objects.filter(
            conversation=conversation, role='assistant',
        ).order_by('-created_at').first()
        self.assertEqual(
            last_msg.content,
            "Time boundary honored. Repeat this structure.",
        )

    @patch('apps.core.ai_orchestrator.cos_context.determine_activation_state',
           return_value='CLEAN')
    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    def test_closure_skips_calibration_recording(
        self, mock_ai, mock_ai_cls, mock_determine_tier
    ):
        """Closure must NOT trigger calibration answer recording."""
        mock_ai.is_available = True
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)

        pa1 = self._build_pa()
        conversation = pa1.get_or_create_conversation()
        pa1.send_message(
            "I'll finish the report by 5pm today. "
            "Done means the report is submitted.",
            conversation=conversation,
        )

        pa2 = self._build_pa()

        with patch(
            'apps.core.blueprint.cos_governance.record_calibration_answer'
        ) as mock_cal:
            pa2.send_message(
                "It's done.",
                conversation=conversation,
            )

        mock_cal.assert_not_called()

    @patch('apps.core.ai_orchestrator.cos_context.determine_activation_state',
           return_value='CLEAN')
    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    def test_closure_skips_rolling_summary(
        self, mock_ai, mock_ai_cls, mock_determine_tier
    ):
        """Closure must NOT trigger rolling summary generation."""
        mock_ai.is_available = True
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)

        pa1 = self._build_pa()
        conversation = pa1.get_or_create_conversation()
        pa1.send_message(
            "I'll finish the report by 5pm today. "
            "Done means the report is submitted.",
            conversation=conversation,
        )

        pa2 = self._build_pa()

        with patch(
            'apps.ai.executive_briefing.maybe_generate_rolling_summary'
        ) as mock_summary:
            pa2.send_message(
                "It's done.",
                conversation=conversation,
            )

        mock_summary.assert_not_called()

    @patch('apps.core.ai_orchestrator.cos_context.determine_activation_state',
           return_value='CLEAN')
    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    def test_closure_resilient_to_db_exception(
        self, mock_ai, mock_ai_cls, mock_determine_tier
    ):
        """
        If conversation.save() throws AFTER closure is detected,
        the sentinel ensures closure response is still returned
        and intent recognition does NOT run.
        """
        mock_ai.is_available = True
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)

        pa1 = self._build_pa()
        conversation = pa1.get_or_create_conversation()
        pa1.send_message(
            "I'll finish the report by 5pm today. "
            "Done means the report is submitted.",
            conversation=conversation,
        )

        pa2 = self._build_pa()

        from apps.ai import intent_service as intent_mod
        recognize_called = {'called': False}

        def track_recognize(*args, **kwargs):
            recognize_called['called'] = True
            return []

        # Patch conversation.save to throw INSIDE the ECC try block
        original_save = conversation.save
        call_count = {'n': 0}

        def flaky_save(*args, **kwargs):
            call_count['n'] += 1
            # Let first saves (user message, etc.) through.
            # Throw on the metadata save inside ECC closure.
            if call_count['n'] >= 4:
                raise RuntimeError("simulated DB failure")
            return original_save(*args, **kwargs)

        with patch.object(
            intent_mod.intent_service, 'recognize_intents',
            side_effect=track_recognize,
        ), patch.object(
            type(conversation), 'save', flaky_save,
        ):
            result = pa2.send_message(
                "It's done.",
                conversation=conversation,
            )

        # Closure response must still be returned
        self.assertIn('response', result)

        # Intent recognition must NOT have been called
        self.assertFalse(
            recognize_called['called'],
            "Intent recognition must not run after closure sentinel is set",
        )

    @patch('apps.core.ai_orchestrator.cos_context.determine_activation_state',
           return_value='CLEAN')
    @patch('apps.ai.personal_assistant.AIService')
    @patch('apps.ai.personal_assistant.ai_service')
    def test_generate_response_closure_skips_llm(
        self, mock_ai, mock_ai_cls, mock_determine_tier
    ):
        """
        _generate_response() closure must return immediately and
        never call the LLM API.
        """
        mock_ai.is_available = True
        mock_ai._call_api = MagicMock(
            return_value="LLM should not run",
        )
        mock_ai_cls.check_user_consent = MagicMock(return_value=True)

        pa1 = self._build_pa()
        conversation = pa1.get_or_create_conversation()
        pa1.send_message(
            "I'll finish the report by 5pm today. "
            "Done means the report is submitted.",
            conversation=conversation,
        )

        pa2 = self._build_pa()

        # Call _generate_response directly to test the inner path
        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context,
            _build_trajectory_signals,
        )
        with patch(
            'apps.core.ai_orchestrator.cos_context.build_cos_context',
            return_value=self._mock_cos_context(),
        ), patch(
            'apps.core.ai_orchestrator.cos_context._build_trajectory_signals',
            return_value={
                'renegotiation_patterns': [],
                'tier1_skip_patterns': [],
                'consecutive_tier1_skips': 0,
            },
        ), patch(
            'apps.core.blueprint.learning_mode.is_learning_mode_active',
            return_value=False,
        ):
            response = pa2._generate_response(
                "Done", conversation,
            )

        self.assertEqual(
            response,
            "Time boundary honored. Repeat this structure.",
        )
        mock_ai._call_api.assert_not_called()
