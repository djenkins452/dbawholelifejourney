"""
Phase 4 CoS — Cross-Domain Intelligence Tests.

Tests for cross-domain correlation rules.
"""

from unittest.mock import patch

from django.test import TestCase

from apps.core.ai_insights.rules_cross_domain import (
    BehavioralInstabilityRule,
    ComplianceRiskRule,
    MotivationDriftRule,
    OvertrainingRiskRule,
)
from apps.users.models import User


class CrossDomainRuleTestBase(TestCase):
    """Base test setup for cross-domain rules."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="crossdomain@test.com", password="testpass123"
        )
        self.base_event = {
            "event_type": "scheduled_check",
            "module": "core",
            "user_state": {},
        }


class MotivationDriftRuleTest(CrossDomainRuleTestBase):
    """Tests for Mood ↓ + Goal Progress ↓ → Motivation Drift."""

    def test_applies_on_scheduled_check(self):
        rule = MotivationDriftRule()
        self.assertTrue(rule.applies(self.user, self.base_event))

    def test_no_insight_when_mood_stable(self):
        rule = MotivationDriftRule()
        event = {
            **self.base_event,
            "user_state": {
                "journal": {"mood_trend": "stable"},
                "goals": {"avg_completion_rate": 0.8, "overdue_goal_count": 0},
            },
        }
        insights = rule.evaluate(self.user, event)
        self.assertEqual(insights, [])

    def test_insight_when_mood_declining_and_goals_failing(self):
        rule = MotivationDriftRule()
        event = {
            **self.base_event,
            "user_state": {
                "journal": {"mood_trend": "declining"},
                "goals": {"avg_completion_rate": 0.2, "overdue_goal_count": 3},
            },
        }
        insights = rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["severity"], "warning")
        self.assertIn("Motivation Drift", insights[0]["title"])

    def test_no_insight_when_goals_ok(self):
        rule = MotivationDriftRule()
        event = {
            **self.base_event,
            "user_state": {
                "journal": {"mood_trend": "declining"},
                "goals": {"avg_completion_rate": 0.8, "overdue_goal_count": 0},
            },
        }
        insights = rule.evaluate(self.user, event)
        self.assertEqual(insights, [])


class OvertrainingRiskRuleTest(CrossDomainRuleTestBase):
    """Tests for Sleep ↓ + Workout Intensity ↑ → Overtraining Risk."""

    def test_no_insight_when_sleep_adequate(self):
        rule = OvertrainingRiskRule()
        event = {
            **self.base_event,
            "user_state": {
                "health": {
                    "sleep_avg_hours_7d": 7.5,
                    "workout_count_7d": 6,
                    "sleep_trend": "stable",
                },
            },
        }
        insights = rule.evaluate(self.user, event)
        self.assertEqual(insights, [])

    def test_insight_when_sleep_low_and_workouts_high(self):
        rule = OvertrainingRiskRule()
        event = {
            **self.base_event,
            "user_state": {
                "health": {
                    "sleep_avg_hours_7d": 5.0,
                    "workout_count_7d": 7,
                    "sleep_trend": "decreasing",
                },
            },
        }
        insights = rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 1)
        self.assertIn("Overtraining", insights[0]["title"])

    def test_no_insight_when_workouts_low(self):
        rule = OvertrainingRiskRule()
        event = {
            **self.base_event,
            "user_state": {
                "health": {
                    "sleep_avg_hours_7d": 5.0,
                    "workout_count_7d": 2,
                    "sleep_trend": "decreasing",
                },
            },
        }
        insights = rule.evaluate(self.user, event)
        self.assertEqual(insights, [])


class ComplianceRiskRuleTest(CrossDomainRuleTestBase):
    """Tests for Weight ↑ + Medication Missed → Compliance Risk."""

    def test_no_insight_when_compliant(self):
        rule = ComplianceRiskRule()
        event = {
            **self.base_event,
            "user_state": {
                "health": {
                    "weight_trend": "increasing",
                    "medication_adherence_pct": 95,
                },
            },
        }
        insights = rule.evaluate(self.user, event)
        self.assertEqual(insights, [])

    def test_insight_when_weight_up_and_meds_missed(self):
        rule = ComplianceRiskRule()
        event = {
            **self.base_event,
            "user_state": {
                "health": {
                    "weight_trend": "increasing",
                    "medication_adherence_pct": 40,
                },
            },
        }
        insights = rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["severity"], "critical")
        self.assertIn("Compliance", insights[0]["title"])


class BehavioralInstabilityRuleTest(CrossDomainRuleTestBase):
    """Tests for Habit Streak Break + Mood ↓ → Behavioral Instability."""

    def test_no_insight_when_habits_strong(self):
        rule = BehavioralInstabilityRule()
        event = {
            **self.base_event,
            "user_state": {
                "habits": {
                    "streak_broken_recently": False,
                    "avg_completion_rate": 0.9,
                },
                "journal": {"mood_trend": "stable"},
            },
        }
        insights = rule.evaluate(self.user, event)
        self.assertEqual(insights, [])

    def test_insight_when_streak_broken_and_mood_declining(self):
        rule = BehavioralInstabilityRule()
        event = {
            **self.base_event,
            "user_state": {
                "habits": {
                    "streak_broken_recently": True,
                    "avg_completion_rate": 0.3,
                },
                "journal": {"mood_trend": "declining"},
            },
        }
        insights = rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 1)
        self.assertIn("Behavioral Instability", insights[0]["title"])
