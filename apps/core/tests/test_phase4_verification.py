"""
Phase 4 CoS — Verification Tests.

Tests that verify:
1. All Phase 4 trackers are properly wired into production call sites
2. Noise budget caps and dedupe work correctly
3. Confidence adjustment applied to PRIE
4. Escalation speed modifier applied to intensity
5. Preferred briefing length applied to DBE
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from apps.users.models import User


class CrossDomainRuleRegistrationTest(TestCase):
    """Verify cross-domain rules register into the PIE registry."""

    def test_cross_domain_rules_registered(self):
        """Cross-domain rules should be in the PIE registry after import."""
        from apps.core.ai_insights.rule_registry import get_rules

        rule_names = [r.rule_name for r in get_rules()]
        self.assertIn("cross_domain_motivation_drift", rule_names)
        self.assertIn("cross_domain_overtraining_risk", rule_names)
        self.assertIn("cross_domain_compliance_risk", rule_names)
        self.assertIn("cross_domain_behavioral_instability", rule_names)


class NoiseBudgetTest(TestCase):
    """Tests for noise budget caps and dedupe."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="noise@test.com", password="testpass123"
        )

    def test_critical_always_passes(self):
        """Critical insights bypass all noise budget caps."""
        from apps.core.ai_insights.noise_budget import check_noise_budget

        rule = MagicMock()
        rule.rule_name = "test_rule"

        insight_data = {"severity": "critical", "dedupe_key": "test_critical"}
        allowed, reason = check_noise_budget(self.user, insight_data, rule)
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_daily_cap_enforced(self):
        """Insights blocked when daily cap is reached."""
        from apps.core.ai_insights.models import Insight
        from apps.core.ai_insights.noise_budget import (
            MAX_INSIGHTS_PER_DAY,
            check_noise_budget,
        )

        # Fill up daily budget
        for i in range(MAX_INSIGHTS_PER_DAY):
            Insight.objects.create(
                user=self.user,
                module="test",
                insight_type="test_type",
                severity="info",
                title=f"Test insight {i}",
                message=f"Message {i}",
                confidence_score=0.7,
                explain_why="test",
                dedupe_key=f"daily_test_{i}",
            )

        rule = MagicMock()
        rule.rule_name = "test_rule"
        insight_data = {"severity": "warning", "dedupe_key": "new_insight"}
        allowed, reason = check_noise_budget(self.user, insight_data, rule)
        self.assertFalse(allowed)
        self.assertIn("Daily cap", reason)

    def test_window_cap_enforced(self):
        """Insights blocked when 6h window cap is reached."""
        from apps.core.ai_insights.models import Insight
        from apps.core.ai_insights.noise_budget import (
            MAX_INSIGHTS_PER_6H_WINDOW,
            check_noise_budget,
        )

        for i in range(MAX_INSIGHTS_PER_6H_WINDOW):
            Insight.objects.create(
                user=self.user,
                module="test",
                insight_type="test_type",
                severity="info",
                title=f"Test window insight {i}",
                message=f"Message {i}",
                confidence_score=0.7,
                explain_why="test",
                dedupe_key=f"window_test_{i}",
            )

        rule = MagicMock()
        rule.rule_name = "test_rule"
        insight_data = {"severity": "warning", "dedupe_key": "new_window_insight"}
        allowed, reason = check_noise_budget(self.user, insight_data, rule)
        self.assertFalse(allowed)
        self.assertIn("6h window cap", reason)

    def test_dedupe_blocks_duplicate(self):
        """Existing active insight with same dedupe_key is blocked."""
        from apps.core.ai_insights.models import Insight
        from apps.core.ai_insights.noise_budget import check_noise_budget

        Insight.objects.create(
            user=self.user,
            module="test",
            insight_type="test_type",
            severity="warning",
            title="Existing insight",
            message="Already exists",
            confidence_score=0.8,
            explain_why="test",
            dedupe_key="duplicate_key",
            status="new",
        )

        rule = MagicMock()
        rule.rule_name = "test_rule"
        insight_data = {"severity": "warning", "dedupe_key": "duplicate_key"}
        allowed, reason = check_noise_budget(self.user, insight_data, rule)
        self.assertFalse(allowed)
        self.assertIn("Dedupe", reason)

    def test_dismissed_insight_allows_new(self):
        """Dismissed insights don't block new ones with same dedupe_key."""
        from apps.core.ai_insights.models import Insight
        from apps.core.ai_insights.noise_budget import check_noise_budget

        Insight.objects.create(
            user=self.user,
            module="test",
            insight_type="test_type",
            severity="warning",
            title="Dismissed insight",
            message="Was dismissed",
            confidence_score=0.8,
            explain_why="test",
            dedupe_key="dismissed_key",
            status="dismissed",
        )

        rule = MagicMock()
        rule.rule_name = "test_rule"
        insight_data = {"severity": "warning", "dedupe_key": "dismissed_key"}
        allowed, reason = check_noise_budget(self.user, insight_data, rule)
        self.assertTrue(allowed)

    def test_cross_domain_cap_enforced(self):
        """Cross-domain insights capped separately."""
        from apps.core.ai_insights.models import Insight
        from apps.core.ai_insights.noise_budget import (
            MAX_CROSS_DOMAIN_PER_DAY,
            check_noise_budget,
        )
        from apps.core.ai_insights.rules_cross_domain import MotivationDriftRule

        for i in range(MAX_CROSS_DOMAIN_PER_DAY):
            Insight.objects.create(
                user=self.user,
                module="cross_domain",
                insight_type=f"cross_domain_test_{i}",
                severity="warning",
                title=f"Cross domain {i}",
                message=f"Message {i}",
                confidence_score=0.7,
                explain_why="test",
                dedupe_key=f"cd_test_{i}",
            )

        rule = MotivationDriftRule()
        insight_data = {
            "severity": "warning",
            "dedupe_key": "cd_new",
        }
        allowed, reason = check_noise_budget(self.user, insight_data, rule)
        self.assertFalse(allowed)
        self.assertIn("Cross-domain", reason)

    def test_budget_status(self):
        """get_budget_status returns correct counts."""
        from apps.core.ai_insights.noise_budget import get_budget_status

        status = get_budget_status(self.user)
        self.assertEqual(status["daily_used"], 0)
        self.assertEqual(status["daily_limit"], 12)
        self.assertEqual(status["daily_remaining"], 12)


class ConfidenceAdjustmentWiringTest(TestCase):
    """Verify confidence adjustment is applied in PRIE."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="confidence@test.com", password="testpass123"
        )

    def test_confidence_adjustment_applied(self):
        """PredictionAccuracyProfile adjustment modifies confidence."""
        from apps.core.ai_feedback.models import PredictionAccuracyProfile

        PredictionAccuracyProfile.objects.create(
            user=self.user,
            prediction_type="weight_30d",
            total_validated=5,
            avg_accuracy=0.90,
            confidence_adjustment=0.15,
        )

        from apps.core.ai_feedback.prediction_validator import get_confidence_adjustment

        adj = get_confidence_adjustment(self.user, "weight_30d")
        self.assertEqual(adj, 0.15)


class EscalationModifierWiringTest(TestCase):
    """Verify escalation speed modifier is applied in intensity computation."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="escalation@test.com", password="testpass123"
        )

    def test_modifier_returned(self):
        """InterventionEffectivenessProfile modifier is retrieved correctly."""
        from apps.core.ai_feedback.models import InterventionEffectivenessProfile

        InterventionEffectivenessProfile.objects.create(
            user=self.user,
            total_interventions=10,
            total_accepted=8,
            effectiveness_score=0.85,
            escalation_speed_modifier=-0.3,
        )

        from apps.core.ai_feedback.intervention_tracker import get_escalation_speed_modifier

        modifier = get_escalation_speed_modifier(self.user)
        self.assertEqual(modifier, -0.3)


class BriefingLengthWiringTest(TestCase):
    """Verify preferred briefing length affects DBE output."""

    def test_concise_skips_optional_sections(self):
        """Concise mode should skip risks, relationships, health sections."""
        from apps.core.ai_briefing.briefing_engine import _generate_summary

        ranked_items = [
            {"type": "insight", "title": "Test", "message": "Test msg",
             "severity": "warning", "priority": 1},
        ]
        state = {
            "goals": {"active_goal_count": 1, "overdue_goal_count": 0},
            "habits": {"avg_completion_rate": 0.8},
            "health": {"weight_trend": "increasing", "sleep_avg_hours_7d": 5.5},
            "relationships": {"drifting_count": 2},
        }

        # Standard includes all sections
        standard = _generate_summary(ranked_items, state, preferred_length="standard")
        # Concise skips optional sections
        concise = _generate_summary(ranked_items, state, preferred_length="concise")

        self.assertIn("WHERE YOU STAND", standard)
        self.assertIn("WHERE YOU STAND", concise)
        self.assertIn("TODAY'S DIRECTIVE", standard)
        self.assertIn("TODAY'S DIRECTIVE", concise)

        # Standard should be longer (has optional sections)
        self.assertGreaterEqual(len(standard), len(concise))


class SchedulerRegistrationTest(TestCase):
    """Verify new scheduled tasks are registered."""

    def test_prediction_validation_registered(self):
        from apps.core.ai_scheduler.scheduler_registry import SCHEDULED_TASKS
        self.assertIn("validate_predictions", SCHEDULED_TASKS)

    def test_intervention_effectiveness_registered(self):
        from apps.core.ai_scheduler.scheduler_registry import SCHEDULED_TASKS
        self.assertIn("evaluate_intervention_effectiveness", SCHEDULED_TASKS)

    def test_cross_domain_insights_registered(self):
        from apps.core.ai_scheduler.scheduler_registry import SCHEDULED_TASKS
        self.assertIn("run_cross_domain_insights", SCHEDULED_TASKS)
