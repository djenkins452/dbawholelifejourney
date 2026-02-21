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
