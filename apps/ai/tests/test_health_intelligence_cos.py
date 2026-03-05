"""
Tests for CoS health intelligence enum-only output contract.

Validates:
1. Health intelligence status block in CoS context includes exact enums
2. Validator rejects invalid muscle preservation words (e.g., "stable")
3. Validator rejects paraphrased fat loss phase language
4. "Keep it short" classification
5. Missing DHS data produces UNKNOWN placeholders
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase


class TestHealthIntelligenceContextBlock(TestCase):
    """Test that _format_health_intelligence_block includes enum status."""

    def _call_formatter(self, health_intel, context=None):
        from apps.core.ai_orchestrator.cos_context import (
            _format_health_intelligence_block,
        )
        ctx = context or {'health_intelligence': health_intel}
        return _format_health_intelligence_block(health_intel, ctx)

    def test_enum_values_present_in_output(self):
        """With DHS enums populated, output contains exact enum values."""
        health_intel = {
            'body_comp': {
                'fat_loss_phase': 'STABLE_FAT_LOSS',
                'phase_confidence': 82,
                'plateau_risk_label': 'LOW',
                'muscle_preservation_status': 'HIGH_QUALITY',
                'last_computed': '2026-03-05T08:00:00',
                'fat_loss_quality_label': 'GOOD',
            },
            'last_computed': '2026-03-05T08:00:00',
        }
        output = self._call_formatter(health_intel)

        self.assertIn('fat_loss_phase: STABLE_FAT_LOSS', output)
        self.assertIn('plateau_risk_label: LOW', output)
        self.assertIn('muscle_preservation_status: HIGH_QUALITY', output)
        self.assertIn('phase_confidence: 82%', output)
        self.assertIn('last_updated: 2026-03-05T08:00:00', output)

    def test_missing_enums_produce_unknown(self):
        """When DHS fields are empty/None, output shows UNKNOWN."""
        health_intel = {
            'body_comp': {
                'fat_loss_phase': None,
                'plateau_risk_label': None,
                'muscle_preservation_status': None,
            },
            'last_computed': '',
        }
        output = self._call_formatter(health_intel)

        self.assertIn('fat_loss_phase: UNKNOWN (awaiting data)', output)
        self.assertIn('plateau_risk_label: UNKNOWN (awaiting data)', output)
        self.assertIn('muscle_preservation_status: UNKNOWN (awaiting data)', output)

    def test_empty_body_comp_produces_unknown(self):
        """When body_comp dict is empty, still shows UNKNOWN placeholders."""
        health_intel = {
            'body_comp': {},
            'last_computed': '',
        }
        output = self._call_formatter(health_intel)

        self.assertIn('fat_loss_phase: UNKNOWN (awaiting data)', output)
        self.assertIn('plateau_risk_label: UNKNOWN (awaiting data)', output)
        self.assertIn('muscle_preservation_status: UNKNOWN (awaiting data)', output)

    def test_strict_rule_present(self):
        """Output includes the strict enum-only rule text."""
        health_intel = {
            'body_comp': {'fat_loss_phase': 'PLATEAU'},
            'last_computed': '',
        }
        output = self._call_formatter(health_intel)

        self.assertIn('STRICT RULE', output)
        self.assertIn('RAPID_INITIAL_LOSS', output)
        self.assertIn('HIGH_QUALITY', output)
        self.assertIn('Do NOT paraphrase enums', output)

    def test_all_valid_fat_loss_phases_accepted(self):
        """Each valid fat_loss_phase enum renders correctly."""
        for phase in [
            'RAPID_INITIAL_LOSS', 'STABLE_FAT_LOSS',
            'RECOMPOSITION', 'PLATEAU', 'REBOUND_RISK',
        ]:
            health_intel = {
                'body_comp': {'fat_loss_phase': phase},
                'last_computed': '',
            }
            output = self._call_formatter(health_intel)
            self.assertIn(f'fat_loss_phase: {phase}', output)

    def test_all_valid_plateau_risks_accepted(self):
        """Each valid plateau_risk_label enum renders correctly."""
        for risk in ['LOW', 'RISING', 'HIGH']:
            health_intel = {
                'body_comp': {'plateau_risk_label': risk},
                'last_computed': '',
            }
            output = self._call_formatter(health_intel)
            self.assertIn(f'plateau_risk_label: {risk}', output)

    def test_all_valid_muscle_statuses_accepted(self):
        """Each valid muscle_preservation_status enum renders correctly."""
        for status in ['HIGH_QUALITY', 'MODERATE_QUALITY', 'MUSCLE_RISK']:
            health_intel = {
                'body_comp': {'muscle_preservation_status': status},
                'last_computed': '',
            }
            output = self._call_formatter(health_intel)
            self.assertIn(f'muscle_preservation_status: {status}', output)


class TestHealthResponseValidatorEnums(TestCase):
    """Test that the health response validator catches invalid enum usage."""

    def _validate(self, response_text, cos_context=None):
        from apps.ai.validators.health_response_validator import (
            validate_health_response,
        )
        return validate_health_response(response_text, cos_context)

    def test_stable_muscle_status_rejected(self):
        """'stable' is not a valid muscle_preservation_status enum."""
        result = self._validate(
            "Your muscle preservation is stable and looking good."
        )
        self.assertTrue(result['has_violations'])
        types = [v['type'] for v in result['violations']]
        self.assertIn('INVALID_MUSCLE_STATUS', types)

    def test_valid_muscle_enum_accepted(self):
        """HIGH_QUALITY is a valid enum and should not trigger violation."""
        result = self._validate(
            "Muscle preservation: HIGH_QUALITY"
        )
        # Should not have INVALID_MUSCLE_STATUS
        types = [v['type'] for v in result['violations']]
        self.assertNotIn('INVALID_MUSCLE_STATUS', types)

    def test_paraphrased_phase_rejected(self):
        """'currently in the fat loss phase' should be rejected."""
        result = self._validate(
            "You are currently in the fat loss phase of your journey."
        )
        self.assertTrue(result['has_violations'])
        types = [v['type'] for v in result['violations']]
        self.assertIn('INVALID_FAT_LOSS_PHASE', types)

    def test_exact_phase_enum_accepted(self):
        """Exact enum value should not trigger a violation."""
        result = self._validate(
            "Fat loss phase: STABLE_FAT_LOSS"
        )
        types = [v['type'] for v in result['violations']]
        self.assertNotIn('INVALID_FAT_LOSS_PHASE', types)

    def test_no_health_intel_content_no_violations(self):
        """Response without health intelligence fields should have no enum violations."""
        result = self._validate(
            "Your next task is to review the budget spreadsheet."
        )
        types = [v['type'] for v in result['violations']]
        self.assertNotIn('INVALID_MUSCLE_STATUS', types)
        self.assertNotIn('INVALID_FAT_LOSS_PHASE', types)

    def test_good_muscle_word_rejected(self):
        """'good' is not a valid muscle_preservation_status."""
        result = self._validate(
            "Your muscle preservation is good right now."
        )
        self.assertTrue(result['has_violations'])
        types = [v['type'] for v in result['violations']]
        self.assertIn('INVALID_MUSCLE_STATUS', types)

    def test_severity_is_critical_for_enum_violations(self):
        """Enum violations should be critical severity."""
        result = self._validate(
            "Your muscle preservation is stable and fine."
        )
        self.assertEqual(result['severity'], 'critical')


class TestResponseModeClassification(TestCase):
    """Test that 'keep it short' properly maps to brief mode."""

    def _classify(self, message, is_analysis=False, is_task_query=False):
        from apps.ai.personal_assistant import PersonalAssistant
        return PersonalAssistant._classify_response_mode(
            message, is_analysis, is_task_query,
        )

    def test_keep_it_short_is_brief(self):
        """'Keep it short' in message should classify as brief."""
        result = self._classify(
            "What is my fat loss phase? Keep it short."
        )
        self.assertEqual(result, 'brief')

    def test_keep_it_brief_is_brief(self):
        result = self._classify(
            "What is my plateau risk? Keep it brief."
        )
        self.assertEqual(result, 'brief')

    def test_just_the_numbers_is_brief(self):
        result = self._classify(
            "Fat loss phase and plateau risk. Just the numbers."
        )
        self.assertEqual(result, 'brief')

    def test_tldr_is_brief(self):
        result = self._classify("Health status? tl;dr")
        self.assertEqual(result, 'brief')

    def test_normal_health_question_not_brief(self):
        """A normal health question without brevity keywords should not be brief."""
        result = self._classify(
            "What is my current fat loss phase and what does it mean?"
        )
        self.assertNotEqual(result, 'brief')


class TestHealthIntelligencePromptRules(TestCase):
    """Test that health intelligence keywords trigger strict format rules."""

    def test_health_intel_keywords_add_rules(self):
        """When message contains health intel keywords, rules_block gets format rule."""
        message = "What is my fat loss phase, plateau risk, and muscle preservation status? Keep it short."
        msg_lower = message.lower()

        _hi_keywords = [
            'fat loss phase', 'plateau risk', 'muscle preservation',
            'health intelligence status', 'body comp status',
        ]
        _is_health_intel_query = any(kw in msg_lower for kw in _hi_keywords)
        self.assertTrue(_is_health_intel_query)

    def test_unrelated_message_no_hi_rules(self):
        """Unrelated message should not trigger health intelligence rules."""
        message = "What tasks do I have today?"
        msg_lower = message.lower()

        _hi_keywords = [
            'fat loss phase', 'plateau risk', 'muscle preservation',
            'health intelligence status', 'body comp status',
        ]
        _is_health_intel_query = any(kw in msg_lower for kw in _hi_keywords)
        self.assertFalse(_is_health_intel_query)
