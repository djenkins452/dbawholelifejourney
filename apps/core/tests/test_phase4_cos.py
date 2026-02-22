"""
Phase 4 CoS — Executive Context Builder + Tone Calibration Tests.

Tests for:
- build_executive_context()
- _determine_tone_mode()
- format_cos_system_injection() with Phase 4 fields
- DBE strategic narrative generation
- WIRE strategic review generation
"""

from unittest.mock import patch, MagicMock

from django.test import TestCase

from apps.users.models import User


class ExecutiveContextBuilderTest(TestCase):
    """Tests for the Phase 4 executive context builder."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="executive@test.com", password="testpass123"
        )

    @patch("apps.core.ai_orchestrator.cos_context.build_cos_context")
    def test_build_executive_context_structure(self, mock_build):
        from apps.core.ai_orchestrator.cos_context import build_executive_context

        mock_build.return_value = {
            'alignment_score': 85,
            'drift_score': 15,
            'weekly_pressure': {'avg_load': 60},
            'risk_warnings': [],
            'active_insights': [],
            'active_predictions': [],
            'relationship_signals': [],
            'mood_status': {'trend': 'stable'},
            'health_signals': {},
            'open_loops': {},
            'feedback_profiles': {},
            'governance_profile': {'accountability_style': 'standard'},
            'capacity_snapshot': {'completed_blocks': 3, 'total_blocks': 8},
            'executive_tone_mode': 'strategic_executive',
            'learned_profile_prompt': '',
        }

        context = build_executive_context(self.user)
        executive = context.get('executive', {})

        self.assertIn('strategic_state_summary', executive)
        self.assertIn('risk_flags', executive)
        self.assertIn('momentum_indicators', executive)
        self.assertIn('pressure_indicators', executive)
        self.assertIn('relational_status', executive)
        self.assertIn('health_status', executive)
        self.assertIn('focus_conflicts', executive)
        self.assertIn('recommended_focus_for_today', executive)
        self.assertIn('noise_items', executive)
        self.assertIn('governance_tier', executive)
        self.assertIn('intervention_level', executive)
        self.assertIn('tone_mode', executive)


class ToneModeTest(TestCase):
    """Tests for executive tone mode selection."""

    def test_strategic_executive_default(self):
        from apps.core.ai_orchestrator.cos_context import _determine_tone_mode

        user = MagicMock()
        context = {
            'drift_score': 10,
            'mood_status': {'trend': 'stable'},
            'weekly_pressure': {'avg_load': 50},
        }
        mode = _determine_tone_mode(user, context)
        self.assertEqual(mode, 'strategic_executive')

    def test_direct_accountability_high_drift(self):
        from apps.core.ai_orchestrator.cos_context import _determine_tone_mode

        user = MagicMock()
        context = {
            'drift_score': 55,
            'mood_status': {'trend': 'stable'},
            'weekly_pressure': {'avg_load': 50},
        }
        mode = _determine_tone_mode(user, context)
        self.assertEqual(mode, 'direct_accountability')

    def test_reflective_support_declining_mood(self):
        from apps.core.ai_orchestrator.cos_context import _determine_tone_mode

        user = MagicMock()
        context = {
            'drift_score': 10,
            'mood_status': {'trend': 'declining'},
            'weekly_pressure': {'avg_load': 50},
        }
        mode = _determine_tone_mode(user, context)
        self.assertEqual(mode, 'reflective_support')

    def test_direct_overrides_reflective_at_high_drift(self):
        from apps.core.ai_orchestrator.cos_context import _determine_tone_mode

        user = MagicMock()
        context = {
            'drift_score': 50,
            'mood_status': {'trend': 'declining'},
            'weekly_pressure': {'avg_load': 90},
        }
        mode = _determine_tone_mode(user, context)
        # High drift takes priority
        self.assertEqual(mode, 'direct_accountability')


class SystemInjectionTest(TestCase):
    """Tests for format_cos_system_injection with Phase 4 fields."""

    def test_includes_insights(self):
        """format_cos_system_injection renders active insights."""
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection

        context = {
            'blueprint_state': {},
            'alignment_score': 85,
            'drift_score': 10,
            'executive_tone_mode': 'strategic_executive',
            'active_insights': [
                {'type': 'weight_trend_up', 'severity': 'warning',
                 'title': 'Weight up', 'module': 'health'},
            ],
            'active_predictions': [],
            'relationship_signals': [],
            'mood_status': {},
            'health_signals': {},
            'open_loops': {},
            'feedback_profiles': {},
            'module_permissions': {},
            'governance_profile': {},
            'learned_profile_prompt': '',
        }
        output = format_cos_system_injection(context)
        # Insights are rendered in the SITUATIONAL AWARENESS block
        self.assertIn("Weight up", output)
        self.assertIn("SITUATIONAL AWARENESS", output)

    def test_tone_mode_in_executive_context(self):
        """executive_tone_mode is stored in executive sub-dict, not in formatter.

        The tone mode is used by build_executive_context (line 906) and
        governance_strategy_prompt (rendered at line 843). The raw
        executive_tone_mode field is NOT rendered as-is by the formatter.
        """
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection

        # When governance_strategy_prompt is provided, it IS rendered
        context = {
            'blueprint_state': {},
            'executive_tone_mode': 'strategic_executive',
            'active_insights': [],
            'active_predictions': [],
            'relationship_signals': [],
            'mood_status': {},
            'health_signals': {},
            'open_loops': {},
            'module_permissions': {},
            'governance_strategy_prompt': 'STRATEGY: Be direct and accountable.',
        }
        output = format_cos_system_injection(context)
        self.assertIn("Be direct and accountable", output)

    def test_learned_profile_not_in_injection(self):
        """learned_profile_prompt is NOT rendered by format_cos_system_injection.

        The learned profile is injected as a separate priority layer in
        personal_assistant.py (Layer 5) to avoid duplication. The formatter
        intentionally skips it. build_cos_context collects it, but the
        formatted output should not include it.
        """
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection

        context = {
            'blueprint_state': {},
            'alignment_score': 85,
            'drift_score': 10,
            'executive_tone_mode': 'strategic_executive',
            'active_insights': [],
            'active_predictions': [],
            'relationship_signals': [],
            'mood_status': {},
            'health_signals': {},
            'open_loops': {},
            'feedback_profiles': {},
            'module_permissions': {},
            'governance_profile': {},
            'learned_profile_prompt': '--- LEARNED USER PROFILE ---\nCore Values: discipline',
        }
        output = format_cos_system_injection(context)
        # Learned profile is injected separately in personal_assistant.py Layer 5,
        # NOT inside the situational awareness block.
        self.assertNotIn("LEARNED USER PROFILE", output)


class WriteSuppressedContractTest(TestCase):
    """Tests for the write-suppressed system prompt contract.

    Validates that the COS_WRITE_SUPPRESSED_CONTRACT is correctly injected
    into the system prompt when writes are suppressed (Learning Mode),
    and that the normal template does NOT include the contract.
    """

    FORBIDDEN_TOKENS = {
        'logged', 'logging', 'saved', 'saving', 'recorded', 'recording',
        'marked', 'marking', 'flagged', 'flagging', 'updated', 'updating',
        'scheduled', 'scheduling', 'noted', 'captured', 'tracked',
        'persist', 'calendar', 'queued', 'will apply',
        'when ready', 'after exit', 'execution resumes',
        'Learning Mode', 'current configuration', 'write suppression',
    }

    def _make_learning_context(self):
        """Minimal learning mode context dict."""
        return {
            'learning_mode': True,
            'module_permissions': {'health': True, 'journal': True},
            'blueprint_state': {'pillars_ranked': ['Health', 'Faith']},
            'protected_tiers': ['Morning workout'],
            'governance_profile': {},
            'persona_profile': {'key': 'supportive'},
            'capacity_snapshot': {},
            'medication_adherence_state': {},
            'active_fast_status': {},
            'calendar_events_today': [],
            'transformation_metrics': {},
            'health_signals': {},
            'user_priorities': [],
        }

    def _make_normal_context(self):
        """Minimal normal (non-learning-mode) context dict."""
        return {
            'blueprint_state': {},
            'executive_tone_mode': 'strategic_executive',
            'active_insights': [],
            'active_predictions': [],
            'relationship_signals': [],
            'mood_status': {},
            'health_signals': {},
            'open_loops': {},
            'module_permissions': {'health': True},
            'trajectory_signals': {},
        }

    def test_learning_mode_includes_contract(self):
        """Learning mode injection includes the write-suppressed contract."""
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection
        ctx = self._make_learning_context()
        output = format_cos_system_injection(ctx)
        self.assertIn("WRITE-SUPPRESSED CONTRACT", output)
        self.assertIn("Writes are suppressed.", output)

    def test_normal_mode_excludes_contract(self):
        """Normal mode injection does NOT include the write-suppressed contract."""
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection
        ctx = self._make_normal_context()
        output = format_cos_system_injection(ctx)
        self.assertNotIn("WRITE-SUPPRESSED CONTRACT", output)
        self.assertNotIn("Writes are suppressed.", output)

    def test_contract_forbids_write_verbs(self):
        """The contract text itself lists all forbidden write verbs."""
        from apps.core.ai_orchestrator.cos_context import COS_WRITE_SUPPRESSED_CONTRACT
        contract = COS_WRITE_SUPPRESSED_CONTRACT
        # Contract must instruct the LLM to avoid these
        self.assertIn("log", contract)
        self.assertIn("save", contract)
        self.assertIn("record", contract)
        self.assertIn("mark", contract)
        self.assertIn("flag", contract)
        self.assertIn("update", contract)
        self.assertIn("schedule", contract)

    def test_contract_forbids_future_promises(self):
        """The contract text forbids future-promise phrasing."""
        from apps.core.ai_orchestrator.cos_context import COS_WRITE_SUPPRESSED_CONTRACT
        contract = COS_WRITE_SUPPRESSED_CONTRACT
        self.assertIn("when", contract.lower())
        self.assertIn("once", contract.lower())
        self.assertIn("resumes", contract.lower())
        self.assertIn("later", contract.lower())

    def test_contract_forbids_mode_names(self):
        """The contract text forbids mentioning internal mode names."""
        from apps.core.ai_orchestrator.cos_context import COS_WRITE_SUPPRESSED_CONTRACT
        contract = COS_WRITE_SUPPRESSED_CONTRACT
        # Contract must tell LLM not to mention these
        self.assertIn("Learning Mode", contract)

    def test_contract_specifies_two_line_response(self):
        """The contract specifies exactly two lines for write-demand responses."""
        from apps.core.ai_orchestrator.cos_context import COS_WRITE_SUPPRESSED_CONTRACT
        contract = COS_WRITE_SUPPRESSED_CONTRACT
        self.assertIn("EXACTLY two lines", contract)
        self.assertIn("Line 1", contract)
        self.assertIn("Line 2", contract)

    def test_learning_mode_no_old_rules_block(self):
        """The old WRITE-SUPPRESSED BEHAVIORAL RULES block is gone."""
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection
        ctx = self._make_learning_context()
        output = format_cos_system_injection(ctx)
        self.assertNotIn("WRITE-SUPPRESSED BEHAVIORAL RULES", output)
        self.assertNotIn("LEARNING MODE AWARENESS", output)

    def test_learning_mode_still_has_priorities(self):
        """Even with write suppression, priorities and non-negotiables are present."""
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection
        ctx = self._make_learning_context()
        output = format_cos_system_injection(ctx)
        self.assertIn("Morning workout", output)
        self.assertIn("Health", output)

    def test_normal_mode_has_cognitive_precision(self):
        """Normal mode always includes Phase 2 cognitive framework.
        Phase 3 trajectory framework only in STRUCTURAL_DRIFT state."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, ACTIVATION_STRUCTURAL_DRIFT,
        )
        ctx = self._make_normal_context()
        ctx['trajectory_activation_state'] = ACTIVATION_STRUCTURAL_DRIFT
        output = format_cos_system_injection(ctx)
        self.assertIn("COGNITIVE PRECISION", output)
        self.assertIn("TRAJECTORY PRECISION", output)

    def test_compliance_gate_still_importable(self):
        """The compliance gate function still exists for backward compatibility."""
        from apps.core.ai_orchestrator.cos_context import apply_output_compliance_gate
        # Should be callable, returns text unchanged when writes_suppressed=False
        result = apply_output_compliance_gate("Test text", writes_suppressed=False)
        self.assertEqual(result, "Test text")


class TieredActivationTest(TestCase):
    """Tests for Phase 3 Tiered Activation (CLEAN / EARLY_EROSION / STRUCTURAL_DRIFT)."""

    def _make_normal_context(self, activation_state=None, trajectory_signals=None):
        """Minimal normal context with optional activation state."""
        from apps.core.ai_orchestrator.cos_context import ACTIVATION_CLEAN
        ctx = {
            'blueprint_state': {},
            'executive_tone_mode': 'strategic_executive',
            'active_insights': [],
            'active_predictions': [],
            'relationship_signals': [],
            'mood_status': {},
            'health_signals': {},
            'open_loops': {},
            'module_permissions': {'health': True},
            'trajectory_signals': trajectory_signals or {},
            'trajectory_activation_state': activation_state or ACTIVATION_CLEAN,
        }
        return ctx

    # ------------------------------------------------------------------
    # Erosion marker detection
    # ------------------------------------------------------------------

    def test_detect_erosion_markers_finds_markers(self):
        """detect_erosion_markers returns matched phrases."""
        from apps.core.ai_orchestrator.cos_context import detect_erosion_markers
        result = detect_erosion_markers("I skipped the workout again. Not a big deal.")
        self.assertIn('again', result)
        self.assertIn('not a big deal', result)

    def test_detect_erosion_markers_case_insensitive(self):
        """Erosion detection is case-insensitive."""
        from apps.core.ai_orchestrator.cos_context import detect_erosion_markers
        result = detect_erosion_markers("It's Fine, I'll handle it Next Week.")
        self.assertIn("it's fine", result)
        self.assertIn('next week', result)

    def test_detect_erosion_markers_no_match(self):
        """Clean input returns empty list."""
        from apps.core.ai_orchestrator.cos_context import detect_erosion_markers
        result = detect_erosion_markers("What is my blood pressure?")
        self.assertEqual(result, [])

    def test_detect_erosion_markers_empty_input(self):
        """Empty/None input returns empty list."""
        from apps.core.ai_orchestrator.cos_context import detect_erosion_markers
        self.assertEqual(detect_erosion_markers(''), [])
        self.assertEqual(detect_erosion_markers(None), [])

    # ------------------------------------------------------------------
    # Activation state determination
    # ------------------------------------------------------------------

    def test_determine_clean_state(self):
        """No thresholds, no erosion markers → CLEAN."""
        from apps.core.ai_orchestrator.cos_context import (
            determine_activation_state, ACTIVATION_CLEAN,
        )
        signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }
        result = determine_activation_state(signals, "What time is my next meeting?")
        self.assertEqual(result, ACTIVATION_CLEAN)

    def test_determine_early_erosion_state(self):
        """No thresholds but erosion markers → EARLY_EROSION."""
        from apps.core.ai_orchestrator.cos_context import (
            determine_activation_state, ACTIVATION_EARLY_EROSION,
        )
        signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }
        result = determine_activation_state(
            signals, "I skipped the workout again. Not a big deal."
        )
        self.assertEqual(result, ACTIVATION_EARLY_EROSION)

    def test_determine_structural_drift_renegotiation(self):
        """Renegotiation threshold met → STRUCTURAL_DRIFT."""
        from apps.core.ai_orchestrator.cos_context import (
            determine_activation_state, ACTIVATION_STRUCTURAL_DRIFT,
        )
        signals = {
            'renegotiation_patterns': [
                {'behavior': 'workout', 'count': 4, 'window_days': 10},
            ],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }
        result = determine_activation_state(signals, "I skipped again")
        self.assertEqual(result, ACTIVATION_STRUCTURAL_DRIFT)

    def test_determine_structural_drift_tier1_skips(self):
        """Tier 1 skip threshold met → STRUCTURAL_DRIFT."""
        from apps.core.ai_orchestrator.cos_context import (
            determine_activation_state, ACTIVATION_STRUCTURAL_DRIFT,
        )
        signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [
                {'behavior': 'bible_reading', 'count': 3, 'window_days': 7},
            ],
            'consecutive_tier1_skips': 0,
        }
        result = determine_activation_state(signals, "whatever")
        self.assertEqual(result, ACTIVATION_STRUCTURAL_DRIFT)

    def test_determine_structural_drift_consecutive(self):
        """Consecutive Tier 1 skips ≥2 → STRUCTURAL_DRIFT."""
        from apps.core.ai_orchestrator.cos_context import (
            determine_activation_state, ACTIVATION_STRUCTURAL_DRIFT,
        )
        signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 3,
        }
        result = determine_activation_state(signals, "not a big deal")
        self.assertEqual(result, ACTIVATION_STRUCTURAL_DRIFT)

    def test_structural_drift_overrides_erosion(self):
        """When thresholds met AND erosion markers present → STRUCTURAL_DRIFT."""
        from apps.core.ai_orchestrator.cos_context import (
            determine_activation_state, ACTIVATION_STRUCTURAL_DRIFT,
        )
        signals = {
            'renegotiation_patterns': [
                {'behavior': 'workout', 'count': 5, 'window_days': 10},
            ],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }
        # Input has erosion markers too — structural should still win
        result = determine_activation_state(
            signals, "I skipped again, it's fine"
        )
        self.assertEqual(result, ACTIVATION_STRUCTURAL_DRIFT)

    # ------------------------------------------------------------------
    # System injection output per state
    # ------------------------------------------------------------------

    def test_clean_state_no_trajectory_framework(self):
        """CLEAN state: no trajectory framework injected."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, ACTIVATION_CLEAN,
        )
        ctx = self._make_normal_context(activation_state=ACTIVATION_CLEAN)
        output = format_cos_system_injection(ctx)
        self.assertIn("COGNITIVE PRECISION", output)
        self.assertNotIn("TRAJECTORY PRECISION", output)
        self.assertNotIn("EARLY EROSION", output)
        self.assertNotIn("72-hour", output.lower())
        self.assertNotIn("30-day", output.lower())

    def test_early_erosion_injects_soft_probe(self):
        """EARLY_EROSION state: soft probe framework, no full trajectory."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, ACTIVATION_EARLY_EROSION,
        )
        ctx = self._make_normal_context(activation_state=ACTIVATION_EARLY_EROSION)
        output = format_cos_system_injection(ctx)
        self.assertIn("COGNITIVE PRECISION", output)
        self.assertIn("EARLY EROSION", output)
        self.assertIn("observational", output.lower())
        # Must NOT contain full trajectory framework
        self.assertNotIn("TRAJECTORY PRECISION", output)
        # Must NOT contain horizon modeling instructions
        self.assertNotIn("LAYER 1", output)
        self.assertNotIn("LAYER 2", output)

    def test_early_erosion_no_projections(self):
        """EARLY_EROSION explicitly forbids 72h and 30d projections."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, ACTIVATION_EARLY_EROSION,
        )
        ctx = self._make_normal_context(activation_state=ACTIVATION_EARLY_EROSION)
        output = format_cos_system_injection(ctx)
        # The framework text must contain "Do NOT produce" directives
        self.assertIn("Do NOT produce 72-hour projections", output)
        self.assertIn("Do NOT produce 30-day identity projections", output)

    def test_early_erosion_forbids_deferral(self):
        """EARLY_EROSION framework contains FORBIDDEN DEFERRAL LANGUAGE block."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, ACTIVATION_EARLY_EROSION,
        )
        ctx = self._make_normal_context(activation_state=ACTIVATION_EARLY_EROSION)
        output = format_cos_system_injection(ctx)
        self.assertIn("FORBIDDEN DEFERRAL LANGUAGE", output)
        # Must list specific forbidden words
        output_lower = output.lower()
        for word in ('tomorrow', 'next week', 'monday', 'later', 'make up', 'catch up', 'start fresh'):
            self.assertIn(word, output_lower,
                          f"Forbidden deferral word '{word}' not found in framework")

    def test_early_erosion_requires_corrective_minimum(self):
        """EARLY_EROSION framework mandates a corrective minimum line."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, ACTIVATION_EARLY_EROSION,
        )
        ctx = self._make_normal_context(activation_state=ACTIVATION_EARLY_EROSION)
        output = format_cos_system_injection(ctx)
        self.assertIn("Corrective minimum", output)
        # Must specify "today" in the corrective minimum instruction
        self.assertIn("today", output.lower())

    def test_early_erosion_sentence_limit(self):
        """EARLY_EROSION framework specifies 3-5 sentence limit."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, ACTIVATION_EARLY_EROSION,
        )
        ctx = self._make_normal_context(activation_state=ACTIVATION_EARLY_EROSION)
        output = format_cos_system_injection(ctx)
        self.assertIn("3–5 sentences", output)

    def test_structural_drift_no_deferral_block(self):
        """STRUCTURAL_DRIFT does NOT contain EARLY_EROSION's deferral block."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, ACTIVATION_STRUCTURAL_DRIFT,
        )
        ctx = self._make_normal_context(activation_state=ACTIVATION_STRUCTURAL_DRIFT)
        output = format_cos_system_injection(ctx)
        self.assertNotIn("FORBIDDEN DEFERRAL LANGUAGE", output)
        self.assertNotIn("EARLY EROSION", output)

    def test_clean_no_deferral_block(self):
        """CLEAN does NOT contain any deferral or erosion framework."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, ACTIVATION_CLEAN,
        )
        ctx = self._make_normal_context(activation_state=ACTIVATION_CLEAN)
        output = format_cos_system_injection(ctx)
        self.assertNotIn("FORBIDDEN DEFERRAL LANGUAGE", output)
        self.assertNotIn("EARLY EROSION", output)
        self.assertNotIn("Corrective minimum", output)

    def test_structural_drift_injects_full_framework(self):
        """STRUCTURAL_DRIFT state: full trajectory framework + signals."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, ACTIVATION_STRUCTURAL_DRIFT,
        )
        signals = {
            'renegotiation_patterns': [
                {'behavior': 'workout', 'count': 4, 'window_days': 10},
            ],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
            'drift_scenario_count_14d': 0,
            'override_count_10d': 0,
            'progress_trend_negative': False,
            'insufficient': [],
        }
        ctx = self._make_normal_context(
            activation_state=ACTIVATION_STRUCTURAL_DRIFT,
            trajectory_signals=signals,
        )
        output = format_cos_system_injection(ctx)
        self.assertIn("COGNITIVE PRECISION", output)
        self.assertIn("TRAJECTORY PRECISION", output)
        self.assertIn("LAYER 1", output)
        self.assertIn("LAYER 2", output)
        self.assertIn("LAYER 3", output)
        self.assertIn("HORIZON MODELING RULES", output)
        # Trajectory signals block present
        self.assertIn("RENEGOTIATION: workout overridden 4x", output)

    def test_structural_drift_always_has_projections(self):
        """STRUCTURAL_DRIFT includes 72h and 30d projection instructions."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, ACTIVATION_STRUCTURAL_DRIFT,
        )
        ctx = self._make_normal_context(activation_state=ACTIVATION_STRUCTURAL_DRIFT)
        output = format_cos_system_injection(ctx)
        self.assertIn("72-hour horizon", output)
        self.assertIn("30-day horizon", output)

    def test_weekly_review_not_affected(self):
        """Layer 3 weekly trajectory framing still present in STRUCTURAL_DRIFT."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, ACTIVATION_STRUCTURAL_DRIFT,
        )
        ctx = self._make_normal_context(activation_state=ACTIVATION_STRUCTURAL_DRIFT)
        output = format_cos_system_injection(ctx)
        self.assertIn("WEEKLY TRAJECTORY FRAMING", output)

    def test_write_suppressed_not_affected(self):
        """Write-suppressed contract logic is unchanged by tiered activation."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, COS_WRITE_SUPPRESSED_CONTRACT,
        )
        ctx = {
            'learning_mode': True,
            'module_permissions': {'health': True},
            'blueprint_state': {},
            'protected_tiers': [],
            'governance_profile': {},
            'persona_profile': {},
            'capacity_snapshot': {},
            'medication_adherence_state': {},
            'active_fast_status': {},
            'calendar_events_today': [],
            'transformation_metrics': {},
            'health_signals': {},
            'user_priorities': [],
        }
        output = format_cos_system_injection(ctx)
        self.assertIn("WRITE-SUPPRESSED CONTRACT", output)
        # No trajectory framework in learning mode
        self.assertNotIn("TRAJECTORY PRECISION", output)
        self.assertNotIn("EARLY EROSION", output)


class DBEStrategicNarrativeTest(TestCase):
    """Tests for the Phase 4 DBE strategic narrative format."""

    def test_narrative_structure(self):
        from apps.core.ai_briefing.briefing_engine import _generate_summary

        ranked_items = [
            {"type": "insight", "title": "Weight up", "message": "Weight trending up.",
             "severity": "warning", "priority": 1, "insight_type": "weight_trend"},
            {"type": "prediction", "title": "Weight 190 in 30d",
             "confidence": 0.8, "priority": 3},
        ]
        state = {
            "goals": {"active_goal_count": 3, "overdue_goal_count": 1},
            "habits": {"avg_completion_rate": 0.75},
            "health": {"weight_trend": "increasing", "sleep_avg_hours_7d": 6.0},
        }
        summary = _generate_summary(ranked_items, state)
        self.assertIn("WHERE YOU STAND", summary)
        self.assertIn("WHAT MATTERS MOST", summary)
        self.assertIn("TODAY'S DIRECTIVE", summary)

    def test_narrative_with_empty_data(self):
        from apps.core.ai_briefing.briefing_engine import _generate_summary

        summary = _generate_summary([], {})
        self.assertIn("WHERE YOU STAND", summary)
        self.assertIn("TODAY'S DIRECTIVE", summary)


class WIREStrategicReviewTest(TestCase):
    """Tests for the Phase 4 WIRE strategic review format."""

    def test_review_structure(self):
        from apps.core.ai_weekly_report.report_engine import _generate_summary

        ranked_items = [
            {"type": "insight", "title": "Goal deadline risk", "severity": "warning"},
            {"type": "prediction", "title": "Weight 185 in 30d", "confidence": 0.75},
            {"type": "state_change", "title": "Weight stable", "significant": True, "label": "Weight stable"},
            {"type": "guidance_acted", "title": "Started morning routine"},
        ]
        state = {
            "goals": {"active_goal_count": 3, "overdue_goal_count": 0},
            "habits": {"avg_completion_rate": 0.85},
        }
        learning = {
            "responsiveness_score": 0.8,
            "total_guidance_seen": 10,
            "total_acted": 7,
        }
        summary = _generate_summary(ranked_items, state, learning)
        self.assertIn("MOMENTUM TRAJECTORY", summary)
        self.assertIn("GOVERNANCE COMPLIANCE", summary)
        self.assertIn("NEXT WEEK EMPHASIS", summary)

    def test_review_with_empty_data(self):
        from apps.core.ai_weekly_report.report_engine import _generate_summary

        summary = _generate_summary([], {}, {"responsiveness_score": 0.5, "total_guidance_seen": 0})
        # With empty data, still produces structured review with defaults
        self.assertIn("MOMENTUM TRAJECTORY", summary)
        self.assertIn("GOVERNANCE COMPLIANCE", summary)
