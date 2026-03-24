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

from django.test import SimpleTestCase, TestCase

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
        # Insights are rendered in the PATTERNS & SIGNALS block
        self.assertIn("Weight up", output)
        self.assertIn("CRITICAL DIRECTIVE", output)

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
        """Erosion detection is case-insensitive and normalizes apostrophes."""
        from apps.core.ai_orchestrator.cos_context import detect_erosion_markers
        result = detect_erosion_markers("It's Fine, I'll handle it Next Week.")
        self.assertIn('its fine', result)
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


class DecisionBranchModelingTest(TestCase):
    """Tests for Phase 4 R1 — Decision Branch Modeling."""

    def _make_context(self, activation_state=None, db_signals=None,
                      traj_signals=None, db_gate=None):
        """Minimal context with decision branch fields."""
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
            'trajectory_signals': traj_signals or {
                'renegotiation_patterns': [],
                'tier1_skip_patterns': [],
                'consecutive_tier1_skips': 0,
            },
            'trajectory_activation_state': activation_state or ACTIVATION_CLEAN,
            'decision_branch_signals': db_signals or {
                'goals_within_14d': [],
                'protected_blocks_today': [],
                'deferrals_7d': 0,
            },
            'decision_branch_gate': db_gate or {'active': False, 'reason': '', 'signals': {}},
        }
        return ctx

    # ------------------------------------------------------------------
    # Decision language detection
    # ------------------------------------------------------------------

    def test_detect_decision_language_matches(self):
        """Decision indicators detected in user input."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        result = _detect_decision_language("Should I skip today?")
        self.assertIn('should i', result)
        self.assertIn('skip today', result)

    def test_detect_decision_language_no_match(self):
        """Non-decision input returns empty list."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        result = _detect_decision_language("What is my blood pressure?")
        self.assertEqual(result, [])

    def test_detect_decision_language_empty(self):
        """Empty/None input returns empty list."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        self.assertEqual(_detect_decision_language(''), [])
        self.assertEqual(_detect_decision_language(None), [])

    # ------------------------------------------------------------------
    # Activation gate — non-activation cases
    # ------------------------------------------------------------------

    def test_gate_inactive_no_decision_language(self):
        """No decision language → gate inactive."""
        from apps.core.ai_orchestrator.cos_context import evaluate_decision_branch_gate
        ctx = self._make_context(db_signals={
            'goals_within_14d': [{'title': 'Lose weight', 'days_remaining': 7}],
            'protected_blocks_today': [],
            'deferrals_7d': 0,
        })
        result = evaluate_decision_branch_gate(ctx, "What is my blood pressure?")
        self.assertFalse(result['active'])

    def test_gate_inactive_decision_language_no_targets(self):
        """Decision language but no alignment targets → gate inactive."""
        from apps.core.ai_orchestrator.cos_context import evaluate_decision_branch_gate
        ctx = self._make_context(db_signals={
            'goals_within_14d': [],
            'protected_blocks_today': [],
            'deferrals_7d': 0,
        })
        result = evaluate_decision_branch_gate(ctx, "Should I go to bed early?")
        self.assertFalse(result['active'])

    def test_gate_inactive_trivial_question(self):
        """Trivial non-decision question → gate inactive."""
        from apps.core.ai_orchestrator.cos_context import evaluate_decision_branch_gate
        ctx = self._make_context()
        result = evaluate_decision_branch_gate(ctx, "What time is it?")
        self.assertFalse(result['active'])

    # ------------------------------------------------------------------
    # Activation gate — activation cases
    # ------------------------------------------------------------------

    def test_gate_active_decision_impacts_goal(self):
        """Decision language + goal within 14d → gate active."""
        from apps.core.ai_orchestrator.cos_context import evaluate_decision_branch_gate
        ctx = self._make_context(db_signals={
            'goals_within_14d': [{'title': 'Lose 10 lbs', 'days_remaining': 5}],
            'protected_blocks_today': [],
            'deferrals_7d': 0,
        })
        result = evaluate_decision_branch_gate(ctx, "Should I skip today's workout?")
        self.assertTrue(result['active'])
        self.assertEqual(result['reason'], 'decision_impacts_goal_deadline')

    def test_gate_active_decision_impacts_protected_block(self):
        """Decision language + protected block → gate active."""
        from apps.core.ai_orchestrator.cos_context import evaluate_decision_branch_gate
        ctx = self._make_context(db_signals={
            'goals_within_14d': [],
            'protected_blocks_today': [{'title': 'Bible reading', 'start': '06:00'}],
            'deferrals_7d': 0,
        })
        result = evaluate_decision_branch_gate(ctx, "Thinking about pushing it to tomorrow")
        self.assertTrue(result['active'])
        self.assertEqual(result['reason'], 'decision_impacts_protected_block')

    def test_gate_active_decision_during_threshold_risk(self):
        """Decision language + threshold risk pattern → gate active."""
        from apps.core.ai_orchestrator.cos_context import evaluate_decision_branch_gate
        ctx = self._make_context(
            traj_signals={
                'renegotiation_patterns': [
                    {'behavior': 'workout', 'count': 4, 'window_days': 10},
                ],
                'tier1_skip_patterns': [],
                'consecutive_tier1_skips': 0,
            },
            db_signals={
                'goals_within_14d': [],
                'protected_blocks_today': [],
                'deferrals_7d': 0,
            },
        )
        result = evaluate_decision_branch_gate(ctx, "Should I reschedule my workout?")
        self.assertTrue(result['active'])
        self.assertEqual(result['reason'], 'decision_during_threshold_risk')

    def test_gate_active_repeated_deferral(self):
        """Decision language + ≥2 deferrals in 7d → gate active."""
        from apps.core.ai_orchestrator.cos_context import evaluate_decision_branch_gate
        ctx = self._make_context(db_signals={
            'goals_within_14d': [],
            'protected_blocks_today': [],
            'deferrals_7d': 3,
        })
        result = evaluate_decision_branch_gate(ctx, "Considering whether to postpone again")
        self.assertTrue(result['active'])
        self.assertEqual(result['reason'], 'repeated_deferral')

    # ------------------------------------------------------------------
    # Injection output per tier
    # ------------------------------------------------------------------

    def test_clean_tier_decision_branch_output(self):
        """CLEAN + active gate → neutral decision branch block."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, ACTIVATION_CLEAN,
        )
        gate = {
            'active': True,
            'reason': 'decision_impacts_goal_deadline',
            'signals': {
                'goals': [{'title': 'Lose 10 lbs', 'days_remaining': 5}],
                'decision_language': True,
            },
        }
        ctx = self._make_context(
            activation_state=ACTIVATION_CLEAN,
            db_gate=gate,
        )
        output = format_cos_system_injection(ctx)
        self.assertIn("DECISION BRANCH MODELING", output)
        self.assertIn("Decision Branch A", output)
        self.assertIn("Decision Branch B", output)
        self.assertIn("Executive Framing", output)
        self.assertIn("DECISION CONTEXT", output)
        self.assertIn("Lose 10 lbs", output)
        self.assertIn("5 days remaining", output)
        # Should NOT have erosion or drift framing
        self.assertNotIn("EROSION CONTAINMENT", output)
        self.assertNotIn("STRUCTURAL DRIFT", output)

    def test_early_erosion_decision_branch_output(self):
        """EARLY_EROSION + active gate → erosion containment framing."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, ACTIVATION_EARLY_EROSION,
        )
        gate = {
            'active': True,
            'reason': 'decision_impacts_protected_block',
            'signals': {
                'protected_blocks': [{'title': 'Bible reading', 'start': '06:00'}],
                'decision_language': True,
            },
        }
        ctx = self._make_context(
            activation_state=ACTIVATION_EARLY_EROSION,
            db_gate=gate,
        )
        output = format_cos_system_injection(ctx)
        self.assertIn("DECISION BRANCH MODELING", output)
        self.assertIn("EROSION CONTAINMENT", output)
        self.assertIn("Do not authorize deferral", output)
        self.assertIn("Bible reading", output)

    def test_structural_drift_decision_branch_output(self):
        """STRUCTURAL_DRIFT + active gate → drift-integrated modeling."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, ACTIVATION_STRUCTURAL_DRIFT,
        )
        gate = {
            'active': True,
            'reason': 'decision_during_threshold_risk',
            'signals': {
                'renegotiations': 3,
                'tier1_skips': 0,
                'consecutive_skips': 0,
                'decision_language': True,
            },
        }
        ctx = self._make_context(
            activation_state=ACTIVATION_STRUCTURAL_DRIFT,
            db_gate=gate,
        )
        output = format_cos_system_injection(ctx)
        self.assertIn("DECISION BRANCH MODELING", output)
        self.assertIn("STRUCTURAL DRIFT", output)
        self.assertIn("72h/30d", output)
        # Trajectory framework should also be present
        self.assertIn("TRAJECTORY PRECISION", output)

    def test_no_gate_no_decision_block(self):
        """Inactive gate → no decision branch block in output."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection, ACTIVATION_CLEAN,
        )
        ctx = self._make_context(activation_state=ACTIVATION_CLEAN)
        output = format_cos_system_injection(ctx)
        self.assertNotIn("DECISION BRANCH MODELING", output)
        self.assertNotIn("DECISION CONTEXT", output)

    def test_no_fabricated_projections(self):
        """Decision branch framework prohibits probability/prediction language."""
        from apps.core.ai_orchestrator.cos_context import (
            DECISION_BRANCH_FRAMEWORK_CLEAN,
            DECISION_BRANCH_FRAMEWORK_EROSION,
            DECISION_BRANCH_FRAMEWORK_DRIFT,
        )
        for fw in [DECISION_BRANCH_FRAMEWORK_CLEAN,
                    DECISION_BRANCH_FRAMEWORK_EROSION,
                    DECISION_BRANCH_FRAMEWORK_DRIFT]:
            self.assertIn("Do NOT predict unknown outcomes", fw)
            self.assertIn("assign probabilities", fw)
            self.assertNotIn("percentage", fw.lower())
            self.assertNotIn("likely", fw.lower())

    def test_overdue_goal_formatting(self):
        """Overdue goals show 'X days overdue' in context block."""
        from apps.core.ai_orchestrator.cos_context import _format_decision_branch_injection
        from apps.core.ai_orchestrator.cos_context import ACTIVATION_CLEAN
        gate = {
            'active': True,
            'reason': 'decision_impacts_goal_deadline',
            'signals': {
                'goals': [{'title': 'Run marathon', 'days_remaining': -3}],
            },
        }
        output = _format_decision_branch_injection(gate, ACTIVATION_CLEAN)
        self.assertIn("3 days overdue", output)

    def test_gate_priority_goal_over_protected(self):
        """Goal deadline takes priority in gate reason when both present."""
        from apps.core.ai_orchestrator.cos_context import evaluate_decision_branch_gate
        ctx = self._make_context(db_signals={
            'goals_within_14d': [{'title': 'Goal A', 'days_remaining': 3}],
            'protected_blocks_today': [{'title': 'Block B', 'start': '08:00'}],
            'deferrals_7d': 5,
        })
        result = evaluate_decision_branch_gate(ctx, "Should I skip this?")
        self.assertTrue(result['active'])
        self.assertEqual(result['reason'], 'decision_impacts_goal_deadline')


class CostOfInactionModelingTest(TestCase):
    """Tests for Phase 4 R2 — Cost-of-Inaction Modeling (CIM)."""

    # ------------------------------------------------------------------
    # Severity evaluator
    # ------------------------------------------------------------------

    def test_severity_low_no_factors(self):
        """No behavior factors → CIM suppressed (R4: deadline alone not enough)."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_cim_severity, ACTIVATION_CLEAN,
        )
        gate = {
            'active': True,
            'reason': 'decision_impacts_goal_deadline',
            'signals': {
                'goals': [{'title': 'Goal A', 'days_remaining': 20}],
            },
        }
        severity = _evaluate_cim_severity(gate, ACTIVATION_CLEAN)
        self.assertFalse(severity['moderate'])
        self.assertEqual(severity['factors'], [])

    def test_severity_low_goal_14d_alone(self):
        """R4: Goal deadline ≤14d alone does NOT trigger CIM."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_cim_severity, ACTIVATION_CLEAN,
        )
        gate = {
            'active': True,
            'reason': 'decision_impacts_goal_deadline',
            'signals': {
                'goals': [{'title': 'Goal A', 'days_remaining': 9}],
            },
            'deferrals_7d': 0,
            'user_input': 'I want to push the deadline.',
        }
        severity = _evaluate_cim_severity(gate, ACTIVATION_CLEAN)
        # Deadline proximity alone is NOT a behavior factor (R4)
        self.assertFalse(severity['moderate'])
        self.assertNotIn('goal_deadline_14d', severity['factors'])

    def test_severity_moderate_overdue(self):
        """Overdue goal → severity Moderate."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_cim_severity, ACTIVATION_CLEAN,
        )
        gate = {
            'active': True,
            'reason': 'decision_impacts_goal_deadline',
            'signals': {
                'goals': [{'title': 'Goal A', 'days_remaining': -3}],
            },
        }
        severity = _evaluate_cim_severity(gate, ACTIVATION_CLEAN)
        self.assertTrue(severity['moderate'])
        self.assertIn('goal_overdue', severity['factors'])

    def test_severity_moderate_deferrals(self):
        """≥2 deferrals in 7d → severity Moderate."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_cim_severity, ACTIVATION_CLEAN,
        )
        gate = {
            'active': True,
            'reason': 'repeated_deferral',
            'signals': {
                'deferrals_7d': 3,
            },
        }
        severity = _evaluate_cim_severity(gate, ACTIVATION_CLEAN)
        self.assertTrue(severity['moderate'])
        self.assertIn('repeated_deferrals', severity['factors'])

    def test_severity_moderate_protected_block(self):
        """Protected block cancellation → severity Moderate."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_cim_severity, ACTIVATION_CLEAN,
        )
        gate = {
            'active': True,
            'reason': 'decision_impacts_protected_block',
            'signals': {
                'protected_blocks': [{'title': 'Workout', 'start': '06:00'}],
            },
        }
        severity = _evaluate_cim_severity(gate, ACTIVATION_CLEAN)
        self.assertTrue(severity['moderate'])
        self.assertIn('protected_block_impact', severity['factors'])

    def test_severity_moderate_abandonment_language(self):
        """R4: Abandonment language in user input → severity Moderate."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_cim_severity, ACTIVATION_CLEAN,
        )
        gate = {
            'active': True,
            'reason': 'decision_impacts_goal_deadline',
            'signals': {
                'goals': [{'title': 'Goal A', 'days_remaining': 9}],
            },
            'user_input': 'I want to stop tracking this goal for a while.',
        }
        severity = _evaluate_cim_severity(gate, ACTIVATION_CLEAN)
        self.assertTrue(severity['moderate'])
        self.assertIn('abandonment_language', severity['factors'])

    def test_severity_low_no_abandonment_no_compounding(self):
        """R4: Single deferral without abandonment → CIM suppressed."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_cim_severity, ACTIVATION_CLEAN,
        )
        gate = {
            'active': True,
            'reason': 'decision_impacts_goal_deadline',
            'signals': {
                'goals': [{'title': 'Goal A', 'days_remaining': 9}],
            },
            'deferrals_7d': 0,
            'user_input': 'I want to push it to the weekend.',
        }
        severity = _evaluate_cim_severity(gate, ACTIVATION_CLEAN)
        self.assertFalse(severity['moderate'])
        self.assertEqual(severity['factors'], [])

    def test_severity_moderate_erosion_tier(self):
        """EARLY_EROSION tier → severity Moderate."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_cim_severity, ACTIVATION_EARLY_EROSION,
        )
        gate = {
            'active': True,
            'reason': 'decision_impacts_goal_deadline',
            'signals': {
                'goals': [{'title': 'Goal A', 'days_remaining': 20}],
            },
        }
        severity = _evaluate_cim_severity(gate, ACTIVATION_EARLY_EROSION)
        self.assertTrue(severity['moderate'])
        self.assertIn('tier_escalated', severity['factors'])

    def test_severity_moderate_drift_tier(self):
        """STRUCTURAL_DRIFT tier → severity Moderate."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_cim_severity, ACTIVATION_STRUCTURAL_DRIFT,
        )
        gate = {
            'active': True,
            'reason': 'decision_during_threshold_risk',
            'signals': {},
        }
        severity = _evaluate_cim_severity(gate, ACTIVATION_STRUCTURAL_DRIFT)
        self.assertTrue(severity['moderate'])
        self.assertIn('tier_escalated', severity['factors'])

    # ------------------------------------------------------------------
    # CIM injection — activation / suppression
    # ------------------------------------------------------------------

    def test_cim_suppressed_low_severity(self):
        """CLEAN + no severity factors → no CIM in output."""
        from apps.core.ai_orchestrator.cos_context import (
            _build_cim_injection, ACTIVATION_CLEAN,
        )
        gate = {
            'active': True,
            'reason': 'decision_impacts_goal_deadline',
            'signals': {
                'goals': [{'title': 'Goal A', 'days_remaining': 20}],
            },
        }
        result = _build_cim_injection(gate, ACTIVATION_CLEAN)
        self.assertEqual(result, '')

    def test_cim_active_clean_with_abandonment(self):
        """R4: CLEAN + abandonment language → CIM renders with 72h block."""
        from apps.core.ai_orchestrator.cos_context import (
            _build_cim_injection, ACTIVATION_CLEAN,
        )
        gate = {
            'active': True,
            'reason': 'decision_impacts_goal_deadline',
            'signals': {
                'goals': [{'title': 'Goal A', 'days_remaining': 9}],
            },
            'user_input': 'I want to drop the goal entirely.',
        }
        result = _build_cim_injection(gate, ACTIVATION_CLEAN)
        self.assertIn("Cost of Inaction", result)
        self.assertIn("72h Window", result)
        self.assertIn("What compresses", result)
        self.assertIn("What compounds", result)
        self.assertIn("What becomes harder", result)
        # 14-30d window renders for abandonment language
        self.assertIn("14–30 Day Window", result)
        # No speculative language
        self.assertNotIn("likely", result.lower())
        self.assertNotIn("probably", result.lower())

    def test_cim_active_erosion(self):
        """EARLY_EROSION tier → CIM with erosion-specific language."""
        from apps.core.ai_orchestrator.cos_context import (
            _build_cim_injection, ACTIVATION_EARLY_EROSION,
        )
        gate = {
            'active': True,
            'reason': 'decision_impacts_goal_deadline',
            'signals': {
                'goals': [{'title': 'Goal A', 'days_remaining': 5}],
            },
        }
        # EARLY_EROSION tier alone qualifies as severity Moderate
        result = _build_cim_injection(gate, ACTIVATION_EARLY_EROSION)
        self.assertIn("Cost of Inaction", result)
        self.assertIn("72h Window", result)
        self.assertIn("erosion", result.lower())
        self.assertIn("No deferral authorization", result)

    def test_cim_active_drift(self):
        """STRUCTURAL_DRIFT → CIM integrates with 72h/30d without duplication."""
        from apps.core.ai_orchestrator.cos_context import (
            _build_cim_injection, ACTIVATION_STRUCTURAL_DRIFT,
        )
        gate = {
            'active': True,
            'reason': 'decision_during_threshold_risk',
            'signals': {
                'renegotiations': 4,
                'tier1_skips': 2,
                'consecutive_skips': 2,
            },
        }
        result = _build_cim_injection(gate, ACTIVATION_STRUCTURAL_DRIFT)
        self.assertIn("Cost of Inaction", result)
        self.assertIn("72h Window", result)
        self.assertIn("do not duplicate", result.lower())
        self.assertIn("Phase 3", result)

    def test_cim_no_speculative_language_in_blocks(self):
        """All CIM block templates are free of speculative language."""
        from apps.core.ai_orchestrator.cos_context import (
            CIM_BLOCK_CLEAN, CIM_BLOCK_EROSION, CIM_BLOCK_DRIFT,
        )
        forbidden = ['likely', 'probably', 'this will cause',
                      "you'll fall behind", 'this could result in']
        for block in [CIM_BLOCK_CLEAN, CIM_BLOCK_EROSION, CIM_BLOCK_DRIFT]:
            lower = block.lower()
            for word in forbidden:
                self.assertNotIn(word, lower,
                                 f"Speculative phrase '{word}' found in CIM block")

    # ------------------------------------------------------------------
    # Full injection integration
    # ------------------------------------------------------------------

    def test_full_injection_includes_cim_when_severe(self):
        """_format_decision_branch_injection includes CIM when severity Moderate."""
        from apps.core.ai_orchestrator.cos_context import (
            _format_decision_branch_injection, ACTIVATION_CLEAN,
        )
        gate = {
            'active': True,
            'reason': 'decision_impacts_goal_deadline',
            'signals': {
                'goals': [{'title': 'Finish project', 'days_remaining': 7}],
            },
            'deferrals_7d': 3,  # R4: behavior factor needed for CIM
            'user_input': 'I want to drop the goal.',
        }
        output = _format_decision_branch_injection(gate, ACTIVATION_CLEAN)
        self.assertIn("DECISION BRANCH MODELING", output)
        self.assertIn("Cost of Inaction", output)
        self.assertIn("DECISION CONTEXT", output)
        self.assertIn("Finish project", output)

    def test_full_injection_excludes_cim_when_low(self):
        """_format_decision_branch_injection excludes CIM when severity Low."""
        from apps.core.ai_orchestrator.cos_context import (
            _format_decision_branch_injection, ACTIVATION_CLEAN,
        )
        gate = {
            'active': True,
            'reason': 'decision_impacts_goal_deadline',
            'signals': {
                'goals': [{'title': 'Long-term goal', 'days_remaining': 25}],
            },
        }
        output = _format_decision_branch_injection(gate, ACTIVATION_CLEAN)
        self.assertIn("DECISION BRANCH MODELING", output)
        self.assertNotIn("Cost of Inaction", output)
        self.assertIn("DECISION CONTEXT", output)

    def test_cim_14_30d_included_for_overdue(self):
        """Overdue goal triggers 14–30 Day Window section."""
        from apps.core.ai_orchestrator.cos_context import (
            _build_cim_injection, ACTIVATION_CLEAN,
        )
        gate = {
            'active': True,
            'reason': 'decision_impacts_goal_deadline',
            'signals': {
                'goals': [{'title': 'Overdue goal', 'days_remaining': -5}],
            },
        }
        result = _build_cim_injection(gate, ACTIVATION_CLEAN)
        self.assertIn("14–30 Day Window", result)
        self.assertIn("Recovery cost increase", result)

    def test_cim_14_30d_included_for_drift_tier(self):
        """STRUCTURAL_DRIFT tier triggers 14–30 Day Window."""
        from apps.core.ai_orchestrator.cos_context import (
            _build_cim_injection, ACTIVATION_STRUCTURAL_DRIFT,
        )
        gate = {
            'active': True,
            'reason': 'decision_during_threshold_risk',
            'signals': {
                'renegotiations': 3,
            },
        }
        result = _build_cim_injection(gate, ACTIVATION_STRUCTURAL_DRIFT)
        self.assertIn("14–30 Day Window", result)

    def test_structural_drift_cim_no_escalation_beyond_phase3(self):
        """STRUCTURAL_DRIFT CIM explicitly preserves Phase 3 boundaries."""
        from apps.core.ai_orchestrator.cos_context import (
            _build_cim_injection, ACTIVATION_STRUCTURAL_DRIFT,
        )
        gate = {
            'active': True,
            'reason': 'decision_during_threshold_risk',
            'signals': {'renegotiations': 4, 'consecutive_skips': 3},
        }
        result = _build_cim_injection(gate, ACTIVATION_STRUCTURAL_DRIFT)
        self.assertIn("No intensification beyond", result)
        self.assertIn("Phase 3", result)


class LexicalHardeningTest(TestCase):
    """Tests for Phase 4 R3 — Lexical Hardening."""

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def test_normalize_strips_punctuation(self):
        """Normalization strips punctuation, preserves words."""
        from apps.core.ai_orchestrator.cos_context import _normalize_input
        self.assertEqual(
            _normalize_input("push the deadline."),
            "push the deadline"
        )
        self.assertEqual(
            _normalize_input("push the deadline,"),
            "push the deadline"
        )
        self.assertEqual(
            _normalize_input("push the deadline?"),
            "push the deadline"
        )

    def test_normalize_collapses_spaces(self):
        """Normalization collapses repeated spaces."""
        from apps.core.ai_orchestrator.cos_context import _normalize_input
        self.assertEqual(
            _normalize_input("push   the    deadline"),
            "push the deadline"
        )

    def test_normalize_apostrophes(self):
        """Normalization strips apostrophes for contraction matching."""
        from apps.core.ai_orchestrator.cos_context import _normalize_input
        self.assertEqual(_normalize_input("I'll"), "ill")
        self.assertEqual(_normalize_input("it's"), "its")
        self.assertEqual(_normalize_input("I'm"), "im")

    def test_normalize_curly_quotes(self):
        """Normalization handles curly apostrophes/quotes."""
        from apps.core.ai_orchestrator.cos_context import _normalize_input
        self.assertEqual(_normalize_input("I\u2019ll"), "ill")
        self.assertEqual(_normalize_input("it\u2019s"), "its")

    def test_normalize_empty(self):
        """Empty/None input returns empty string."""
        from apps.core.ai_orchestrator.cos_context import _normalize_input
        self.assertEqual(_normalize_input(''), '')
        self.assertEqual(_normalize_input(None), '')

    # ------------------------------------------------------------------
    # Expanded decision indicators
    # ------------------------------------------------------------------

    def test_deferral_by_action_push_the(self):
        """'push the deadline' matches via 'push the' indicator."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        result = _detect_decision_language("I'm going to push the deadline again.")
        self.assertIn('push the', result)

    def test_deferral_by_action_moved_this(self):
        """'moved this' matches."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        result = _detect_decision_language("I moved this twice already.")
        self.assertIn('moved this', result)

    def test_deferral_by_action_move_it(self):
        """'move it' matches."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        result = _detect_decision_language("I'm about to move it a third time.")
        self.assertIn('move it', result)

    def test_explicit_delay_decide_later(self):
        """'decide later' matches."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        result = _detect_decision_language("I'll decide later.")
        self.assertIn('decide later', result)

    def test_explicit_delay_not_happening(self):
        """'not happening this' matches."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        result = _detect_decision_language("It's just not happening this week.")
        self.assertIn('not happening this', result)

    def test_time_abandonment_restart_next_month(self):
        """'restart next month' matches."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        result = _detect_decision_language("I'll restart next month.")
        self.assertIn('restart next month', result)

    def test_commitment_withdrawal_stop_tracking(self):
        """'stop tracking' matches."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        result = _detect_decision_language("I want to stop tracking it for a while.")
        self.assertIn('stop tracking', result)

    def test_renegotiation_acknowledgement(self):
        """'renegotiating this' matches."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        result = _detect_decision_language("I'm tired of renegotiating this.")
        self.assertIn('renegotiating this', result)

    def test_flat_refusal_not_doing_it(self):
        """'im not doing it' matches (apostrophe normalized)."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        result = _detect_decision_language("I'm not doing it tonight. Period.")
        self.assertIn('im not doing it', result)
        self.assertIn('not doing it tonight', result)

    def test_punctuation_does_not_block_match(self):
        """Punctuation after phrases doesn't prevent matching."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        # "push the" should match even with comma/period/question mark
        for text in [
            "I'll push the deadline.",
            "I'll push the deadline,",
            "Push the deadline?",
        ]:
            result = _detect_decision_language(text)
            self.assertIn('push the', result, f"Failed for: {text}")

    def test_no_false_positive_generic_conversation(self):
        """Generic conversation without decision intent → no match."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        benign = [
            "What is my blood pressure?",
            "Show me my schedule for today.",
            "How did I sleep last night?",
            "Tell me about my goals.",
            "Good morning.",
        ]
        for text in benign:
            result = _detect_decision_language(text)
            self.assertEqual(result, [], f"False positive for: {text}")

    # ------------------------------------------------------------------
    # Expanded erosion markers
    # ------------------------------------------------------------------

    def test_erosion_next_month(self):
        """'next month' now detected as erosion marker."""
        from apps.core.ai_orchestrator.cos_context import detect_erosion_markers
        result = detect_erosion_markers("I'll restart next month.")
        self.assertIn('next month', result)

    def test_erosion_not_happening(self):
        """'not happening' detected as erosion marker."""
        from apps.core.ai_orchestrator.cos_context import detect_erosion_markers
        result = detect_erosion_markers("It's not happening this week.")
        self.assertIn('not happening', result)

    def test_erosion_not_ready(self):
        """'not ready yet' and 'not ready to face' detected."""
        from apps.core.ai_orchestrator.cos_context import detect_erosion_markers
        result1 = detect_erosion_markers("I'm not ready yet.")
        self.assertIn('not ready yet', result1)
        result2 = detect_erosion_markers("I'm not ready to face it.")
        self.assertIn('not ready to face', result2)

    def test_erosion_when_things_calm_down(self):
        """'when things calm down' detected."""
        from apps.core.ai_orchestrator.cos_context import detect_erosion_markers
        result = detect_erosion_markers("I'll get back to it when things calm down.")
        self.assertIn('when things calm down', result)

    def test_erosion_eventually_someday(self):
        """'eventually' and 'someday' detected."""
        from apps.core.ai_orchestrator.cos_context import detect_erosion_markers
        result = detect_erosion_markers("I'll get to it eventually. Someday.")
        self.assertIn('eventually', result)
        self.assertIn('someday', result)

    def test_erosion_for_now(self):
        """'for now' detected."""
        from apps.core.ai_orchestrator.cos_context import detect_erosion_markers
        result = detect_erosion_markers("I'm done for now.")
        self.assertIn('for now', result)

    def test_erosion_ill_try_variants(self):
        """'ill try next week/month' detected (apostrophe normalized)."""
        from apps.core.ai_orchestrator.cos_context import detect_erosion_markers
        result = detect_erosion_markers("I'll try next week.")
        self.assertIn('ill try next week', result)

    # ------------------------------------------------------------------
    # Gate integration with expanded indicators
    # ------------------------------------------------------------------

    def _make_context(self, db_signals=None, traj_signals=None):
        """Minimal context for gate tests."""
        return {
            'trajectory_signals': traj_signals or {
                'renegotiation_patterns': [],
                'tier1_skip_patterns': [],
                'consecutive_tier1_skips': 0,
            },
            'decision_branch_signals': db_signals or {
                'goals_within_14d': [
                    {'title': 'Complete compensation model', 'days_remaining': 9},
                ],
                'protected_blocks_today': [
                    {'title': 'Morning workout', 'start': '06:00'},
                ],
                'deferrals_7d': 3,
            },
        }

    def test_stress_prompt_1_now_triggers(self):
        """#1: 'push the deadline' now activates gate."""
        from apps.core.ai_orchestrator.cos_context import evaluate_decision_branch_gate
        ctx = self._make_context()
        result = evaluate_decision_branch_gate(
            ctx, "I'm going to push the deadline item again. I'm wiped out and it can wait."
        )
        self.assertTrue(result['active'])

    def test_stress_prompt_2_now_triggers(self):
        """#2: 'moved this' / 'move it' / 'not happening this' now activates gate."""
        from apps.core.ai_orchestrator.cos_context import evaluate_decision_branch_gate
        ctx = self._make_context()
        result = evaluate_decision_branch_gate(
            ctx, "I moved this twice already, and I'm about to move it a third time. "
                 "It's just not happening this week."
        )
        self.assertTrue(result['active'])

    def test_stress_prompt_4_now_triggers(self):
        """#4: 'decide later' now activates gate."""
        from apps.core.ai_orchestrator.cos_context import evaluate_decision_branch_gate
        ctx = self._make_context()
        result = evaluate_decision_branch_gate(
            ctx, "I'll decide later. I know it's due soon, but I don't have the bandwidth tonight."
        )
        self.assertTrue(result['active'])

    def test_stress_prompt_6_now_triggers(self):
        """#6: 'restart next month' now activates gate."""
        from apps.core.ai_orchestrator.cos_context import evaluate_decision_branch_gate
        ctx = self._make_context()
        result = evaluate_decision_branch_gate(
            ctx, "This goal is overdue, but I'm not ready to face it. I'll restart next month."
        )
        self.assertTrue(result['active'])

    def test_stress_prompt_6_original_now_triggers(self):
        """#6 (original): 'supposed to start' / 'it never happens' activates."""
        from apps.core.ai_orchestrator.cos_context import evaluate_decision_branch_gate
        ctx = self._make_context()
        result = evaluate_decision_branch_gate(
            ctx, "I was supposed to start this project last Monday. I keep saying "
                 "\u201cnext week\u201d and it never happens."
        )
        self.assertTrue(result['active'])

    def test_supposed_to_start_detected(self):
        """'supposed to start' detected as decision indicator."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        result = _detect_decision_language("I was supposed to start this last week.")
        self.assertIn('supposed to start', result)

    def test_it_never_happens_detected(self):
        """'it never happens' detected as decision indicator."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        result = _detect_decision_language("I keep saying next week and it never happens.")
        self.assertIn('it never happens', result)

    def test_keep_saying_detected(self):
        """'keep saying' detected as decision indicator."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        result = _detect_decision_language("I keep saying I'll do it tomorrow.")
        self.assertIn('keep saying', result)

    def test_keep_pushing_detected(self):
        """'keep pushing' detected as decision indicator."""
        from apps.core.ai_orchestrator.cos_context import _detect_decision_language
        result = _detect_decision_language("I keep pushing this to next week.")
        self.assertIn('keep pushing', result)

    def test_stress_prompt_9_now_triggers(self):
        """#9: 'renegotiating this' + 'stop tracking' now activates gate."""
        from apps.core.ai_orchestrator.cos_context import evaluate_decision_branch_gate
        ctx = self._make_context()
        result = evaluate_decision_branch_gate(
            ctx, "I'm tired of renegotiating this. I want to stop tracking it for a while."
        )
        self.assertTrue(result['active'])

    def test_stress_prompt_10_suppressed_without_target(self):
        """#10: flat refusal without alignment target → suppressed."""
        from apps.core.ai_orchestrator.cos_context import evaluate_decision_branch_gate
        ctx_empty = {
            'trajectory_signals': {
                'renegotiation_patterns': [],
                'tier1_skip_patterns': [],
                'consecutive_tier1_skips': 0,
            },
            'decision_branch_signals': {
                'goals_within_14d': [],
                'protected_blocks_today': [],
                'deferrals_7d': 0,
            },
        }
        result = evaluate_decision_branch_gate(
            ctx_empty, "I'm not doing it tonight. Period."
        )
        self.assertFalse(result['active'])

    def test_stress_prompt_10_activates_with_target(self):
        """#10: flat refusal WITH alignment target → activates."""
        from apps.core.ai_orchestrator.cos_context import evaluate_decision_branch_gate
        ctx = self._make_context()
        result = evaluate_decision_branch_gate(
            ctx, "I'm not doing it tonight. Period."
        )
        self.assertTrue(result['active'])


class EnforcementEscalationLadderTest(TestCase):
    """Tests for Phase 4 R5 — Enforcement Escalation Ladder."""

    def _make_gate(self, user_input='', deferrals_7d=0):
        """Build minimal gate_result for enforcement tests."""
        return {
            'active': True,
            'reason': 'decision_impacts_goal_deadline',
            'signals': {
                'goals': [{'title': 'Goal A', 'days_remaining': 9}],
            },
            'user_input': user_input,
            'deferrals_7d': deferrals_7d,
        }

    # ------------------------------------------------------------------
    # Level evaluation
    # ------------------------------------------------------------------

    def test_level_0_clean_deliberation(self):
        """Clean deliberation with no deferral → Level 0."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_enforcement_level, ACTIVATION_CLEAN,
        )
        gate = self._make_gate(user_input='Should I do this tonight or tomorrow?')
        self.assertEqual(_evaluate_enforcement_level(gate, ACTIVATION_CLEAN), 0)

    def test_level_1_single_deferral(self):
        """Single push/defer action → Level 1."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_enforcement_level, ACTIVATION_CLEAN,
        )
        gate = self._make_gate(user_input='I want to push the deadline.')
        self.assertEqual(_evaluate_enforcement_level(gate, ACTIVATION_CLEAN), 1)

    def test_level_1_erosion_markers(self):
        """Erosion markers without deferrals → Level 1."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_enforcement_level, ACTIVATION_CLEAN,
        )
        gate = self._make_gate(user_input='It\u2019s not a big deal, just this once.')
        self.assertEqual(_evaluate_enforcement_level(gate, ACTIVATION_CLEAN), 1)

    def test_level_2_repeated_deferrals(self):
        """deferrals_7d >= 2 → Level 2."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_enforcement_level, ACTIVATION_CLEAN,
        )
        gate = self._make_gate(
            user_input='I moved this again.',
            deferrals_7d=3,
        )
        self.assertEqual(_evaluate_enforcement_level(gate, ACTIVATION_CLEAN), 2)

    def test_level_2_abandonment_language(self):
        """Abandonment language → Level 2."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_enforcement_level, ACTIVATION_CLEAN,
        )
        gate = self._make_gate(user_input='I want to drop the goal entirely.')
        self.assertEqual(_evaluate_enforcement_level(gate, ACTIVATION_CLEAN), 2)

    def test_level_2_erosion_tier(self):
        """EARLY_EROSION tier → Level 2."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_enforcement_level, ACTIVATION_EARLY_EROSION,
        )
        gate = self._make_gate(user_input='Thinking about this goal.')
        self.assertEqual(_evaluate_enforcement_level(gate, ACTIVATION_EARLY_EROSION), 2)

    def test_level_3_deferrals_plus_abandonment(self):
        """Repeated deferrals + abandonment → Level 3."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_enforcement_level, ACTIVATION_CLEAN,
        )
        gate = self._make_gate(
            user_input='I want to stop tracking this.',
            deferrals_7d=3,
        )
        self.assertEqual(_evaluate_enforcement_level(gate, ACTIVATION_CLEAN), 3)

    def test_level_3_erosion_tier_plus_deferrals(self):
        """EARLY_EROSION + repeated deferrals → Level 3."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_enforcement_level, ACTIVATION_EARLY_EROSION,
        )
        gate = self._make_gate(
            user_input='I\u2019ll push it again.',
            deferrals_7d=2,
        )
        self.assertEqual(_evaluate_enforcement_level(gate, ACTIVATION_EARLY_EROSION), 3)

    def test_level_3_abandonment_plus_erosion_markers(self):
        """Abandonment + erosion markers → Level 3."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_enforcement_level, ACTIVATION_CLEAN,
        )
        gate = self._make_gate(
            user_input='I\u2019m giving up. It\u2019s not a big deal anyway.',
        )
        self.assertEqual(_evaluate_enforcement_level(gate, ACTIVATION_CLEAN), 3)

    def test_drift_does_not_force_level_3(self):
        """STRUCTURAL_DRIFT alone does NOT force Level 3."""
        from apps.core.ai_orchestrator.cos_context import (
            _evaluate_enforcement_level, ACTIVATION_STRUCTURAL_DRIFT,
        )
        gate = self._make_gate(user_input='Should I do this tonight?')
        level = _evaluate_enforcement_level(gate, ACTIVATION_STRUCTURAL_DRIFT)
        self.assertLess(level, 3)

    # ------------------------------------------------------------------
    # Directive generation (R5B)
    # ------------------------------------------------------------------

    def test_directive_level_0_deliberation(self):
        """Level 0 + deliberation → 'Execute {subject} as scheduled.'"""
        from apps.core.ai_orchestrator.cos_context import _generate_enforcement_directive
        gate = self._make_gate(user_input='Should I do this tonight?')
        d = _generate_enforcement_directive(0, gate)
        self.assertIn('as scheduled', d)
        self.assertNotIn('e.g.', d)
        self.assertLessEqual(len(d.split()), 18)

    def test_directive_level_1_deferral(self):
        """Level 1 + deferral → firm boundary with subject."""
        from apps.core.ai_orchestrator.cos_context import _generate_enforcement_directive
        gate = self._make_gate(user_input='I want to push the deadline.')
        d = _generate_enforcement_directive(1, gate)
        self.assertIn('Do not reschedule', d)
        self.assertIn('goal a', d.lower())
        self.assertNotIn('e.g.', d)
        self.assertLessEqual(len(d.split()), 18)

    def test_directive_level_2_abandonment(self):
        """Level 2 + abandonment → containment with subject."""
        from apps.core.ai_orchestrator.cos_context import _generate_enforcement_directive
        gate = self._make_gate(user_input='I want to drop the goal.')
        d = _generate_enforcement_directive(2, gate)
        self.assertIn('abandon', d.lower())
        self.assertIn('goal a', d.lower())
        self.assertNotIn('e.g.', d)
        self.assertLessEqual(len(d.split()), 18)

    def test_directive_level_3_abandonment(self):
        """Level 3 + abandonment → shortest command with subject."""
        from apps.core.ai_orchestrator.cos_context import _generate_enforcement_directive
        gate = self._make_gate(user_input='I\u2019m giving up on this.')
        d = _generate_enforcement_directive(3, gate)
        self.assertIn('pattern ends', d.lower())
        self.assertIn('goal a', d.lower())
        self.assertNotIn('e.g.', d)
        self.assertLessEqual(len(d.split()), 18)

    def test_directive_no_meta_language(self):
        """No directive contains meta-language words."""
        from apps.core.ai_orchestrator.cos_context import _generate_enforcement_directive
        forbidden = ['e.g.', 'for example', 'such as', 'directive', 'statement']
        for level in range(4):
            gate = self._make_gate(user_input='I want to push the deadline.')
            d = _generate_enforcement_directive(level, gate)
            for word in forbidden:
                self.assertNotIn(word, d.lower(), f"Meta-language '{word}' in L{level}: {d}")

    def test_directive_no_exclamation_or_question(self):
        """No directive contains exclamation marks or question marks."""
        from apps.core.ai_orchestrator.cos_context import _generate_enforcement_directive
        for level in range(4):
            gate = self._make_gate(user_input='I want to drop the goal entirely.')
            d = _generate_enforcement_directive(level, gate)
            self.assertNotIn('!', d, f"Exclamation in L{level}: {d}")
            self.assertNotIn('?', d, f"Question in L{level}: {d}")

    def test_directive_protected_block_subject(self):
        """Protected block gate → directive references block title."""
        from apps.core.ai_orchestrator.cos_context import _generate_enforcement_directive
        gate = {
            'active': True,
            'reason': 'decision_impacts_protected_block',
            'signals': {'protected_blocks': [{'title': 'Morning Workout', 'start': '06:00'}]},
            'user_input': 'I want to cancel my workout block.',
            'deferrals_7d': 0,
        }
        d = _generate_enforcement_directive(2, gate)
        self.assertIn('morning workout', d.lower())

    # ------------------------------------------------------------------
    # Framing in injection output (R5B)
    # ------------------------------------------------------------------

    def test_framing_rendered_in_output(self):
        """Framework output contains rendered directive, not meta-text."""
        from apps.core.ai_orchestrator.cos_context import (
            _format_decision_branch_injection, ACTIVATION_CLEAN,
        )
        gate = self._make_gate(user_input='Should I do this tonight?')
        output = _format_decision_branch_injection(gate, ACTIVATION_CLEAN)
        # Must contain rendered directive
        self.assertIn('execute goal a as scheduled', output.lower())
        # Must NOT contain meta-text
        self.assertNotIn('e.g.', output)
        self.assertNotIn('One-line', output)
        self.assertNotIn('directive', output.lower())

    def test_framing_level_2_rendered(self):
        """Level 2 output contains containment directive, not instructions."""
        from apps.core.ai_orchestrator.cos_context import (
            _format_decision_branch_injection, ACTIVATION_CLEAN,
        )
        gate = self._make_gate(user_input='I want to drop the goal.')
        output = _format_decision_branch_injection(gate, ACTIVATION_CLEAN)
        self.assertIn('Do not abandon', output)
        self.assertNotIn('boundary-setting', output.lower())

    def test_framing_level_3_rendered(self):
        """Level 3 output contains control assertion, not instructions."""
        from apps.core.ai_orchestrator.cos_context import (
            _format_decision_branch_injection, ACTIVATION_CLEAN,
        )
        gate = self._make_gate(
            user_input='I\u2019m giving up. It\u2019s not a big deal.',
        )
        output = _format_decision_branch_injection(gate, ACTIVATION_CLEAN)
        self.assertIn('This pattern ends now', output)
        self.assertNotIn('Shortest possible', output)


class ExerciseProgressInCoSTest(SimpleTestCase):
    """Tests that per-exercise progress data flows through to Beth's prompt.

    Uses SimpleTestCase — all tests work with pre-built context dicts or mocks,
    no database needed.
    """

    def _make_context_with_exercise_progress(self, exercise_progress):
        """Build a minimal CoS context dict with exercise_progress in health_signals."""
        return {
            'health_signals': {
                'exercise_progress': exercise_progress,
                'workout_count_7d': 3,
            },
            'active_insights': [],
            'active_predictions': [],
            'active_guidance': [],
            'cross_domain_correlations': [],
        }

    def test_exercise_progress_rendered_in_prompt(self):
        """Exercise progress data appears in the formatted prompt output."""
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection

        context = self._make_context_with_exercise_progress([
            {
                'exercise': 'Bench Press',
                'status': 'plateau',
                'trend': 'flat',
                'sets_30d': 18,
                'prs_30d': 0,
                'best_e1rm': 208.1,
                'recent_e1rm': 208.1,
                'prior_e1rm': 207.0,
                'sessions_30d': 6,
            },
            {
                'exercise': 'Squat',
                'status': 'improving',
                'trend': 'up',
                'sets_30d': 24,
                'prs_30d': 2,
                'best_e1rm': 315.0,
                'recent_e1rm': 315.0,
                'prior_e1rm': 295.0,
                'sessions_30d': 6,
            },
        ])
        output = format_cos_system_injection(context)
        self.assertIn('EXERCISE PROGRESS', output)
        self.assertIn('Bench Press', output)
        self.assertIn('plateau', output)
        self.assertIn('Squat', output)
        self.assertIn('improving', output)

    def test_exercise_progress_shows_pr_count(self):
        """PR count is rendered when > 0."""
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection

        context = self._make_context_with_exercise_progress([
            {
                'exercise': 'Deadlift',
                'status': 'improving',
                'trend': 'up',
                'sets_30d': 12,
                'prs_30d': 3,
                'best_e1rm': 405.0,
                'recent_e1rm': 405.0,
                'prior_e1rm': 380.0,
                'sessions_30d': 4,
            },
        ])
        output = format_cos_system_injection(context)
        self.assertIn('3 PRs this month', output)
        self.assertIn('e1RM 405', output)

    def test_exercise_progress_shows_singular_pr(self):
        """Single PR rendered without 's'."""
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection

        context = self._make_context_with_exercise_progress([
            {
                'exercise': 'OHP',
                'status': 'improving',
                'trend': 'up',
                'sets_30d': 8,
                'prs_30d': 1,
                'best_e1rm': 135.0,
                'recent_e1rm': 135.0,
                'prior_e1rm': 130.0,
                'sessions_30d': 3,
            },
        ])
        output = format_cos_system_injection(context)
        self.assertIn('1 PR this month', output)
        self.assertNotIn('1 PRs', output)

    def test_no_exercise_progress_no_section(self):
        """When exercise_progress is empty, section is omitted."""
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection

        context = self._make_context_with_exercise_progress([])
        output = format_cos_system_injection(context)
        self.assertNotIn('EXERCISE PROGRESS', output)

    def test_exercise_progress_missing_from_health_signals(self):
        """When exercise_progress key is missing entirely, no crash."""
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection

        context = {
            'health_signals': {'workout_count_7d': 3},
            'active_insights': [],
            'active_predictions': [],
            'active_guidance': [],
            'cross_domain_correlations': [],
        }
        output = format_cos_system_injection(context)
        self.assertNotIn('EXERCISE PROGRESS', output)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    @patch('apps.core.ai_state.state_engine.get_state_value', return_value=None)
    def test_exercise_progress_flows_from_sae_to_health_signals(
        self, mock_get_sv, mock_get_state
    ):
        """_build_health_and_vitals grabs exercise_progress from fitness state."""
        from apps.core.ai_orchestrator.cos_context import _build_health_and_vitals

        mock_user = MagicMock()
        mock_user.pk = 999

        mock_get_state.return_value = {
            'workouts_7d': 4,
            'exercise_progress': [
                {
                    'exercise': 'Bench Press',
                    'status': 'plateau',
                    'trend': 'flat',
                    'sets_30d': 18,
                    'prs_30d': 0,
                    'best_e1rm': 208.1,
                    'recent_e1rm': 208.1,
                },
            ],
        }

        result = _build_health_and_vitals(mock_user)

        health_signals = result.get('health_signals', {})
        self.assertIn('exercise_progress', health_signals)
        self.assertEqual(len(health_signals['exercise_progress']), 1)
        self.assertEqual(health_signals['exercise_progress'][0]['exercise'], 'Bench Press')
