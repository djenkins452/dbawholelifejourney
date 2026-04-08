"""
Phase 5 — Feature Gating tests.

Covers the gate fixes added to the signal pipeline:

1. build_nutrition_state returns {"enabled": False} when the
   features.health.nutrition sub-feature is off.
2. build_health_state returns {"enabled": False} when the
   health module is off.
3. build_finance_state returns {"enabled": False} when the
   finance module is off.
4. Insight rules (MotivationDrift, OvertrainingRisk,
   ComplianceRisk, WorkoutConsistency, FastingConsistency)
   return [] when their underlying domain(s) are disabled —
   no more fabricated "perfect" insights from defaulted values.
"""

from datetime import date
from unittest.mock import MagicMock

from django.conf import settings
from django.test import TestCase

from apps.users.models import User


def _make_user(email, **pref_overrides):
    """Create an onboarded user with optional preference overrides."""
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(
        email=email, password="testpass123", date_of_birth=date(1990, 1, 1),
    )
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    prefs = user.preferences
    prefs.has_completed_onboarding = True
    for k, v in pref_overrides.items():
        setattr(prefs, k, v)
    prefs.save()
    return user


# ── Builder gating ───────────────────────────────────────────────────

class NutritionStateGateTests(TestCase):
    def test_disabled_nutrition_returns_enabled_false(self):
        user = _make_user(
            "nutrition_off@test.com",
            health_features={"nutrition": False},
        )
        from apps.core.ai_state.state_builder import build_nutrition_state
        state = build_nutrition_state(user)
        self.assertEqual(state, {"enabled": False})

    def test_disabled_parent_health_disables_nutrition(self):
        user = _make_user(
            "health_off_nutrition@test.com",
            health_enabled=False,
        )
        from apps.core.ai_state.state_builder import build_nutrition_state
        state = build_nutrition_state(user)
        self.assertEqual(state, {"enabled": False})

    def test_enabled_nutrition_builds_full_dict(self):
        user = _make_user("nutrition_on@test.com")
        from apps.core.ai_state.state_builder import build_nutrition_state
        state = build_nutrition_state(user)
        # enabled must be present and True, plus the full query suite runs
        self.assertEqual(state.get("enabled"), True)


class HealthStateGateTests(TestCase):
    def test_disabled_health_returns_enabled_false(self):
        user = _make_user("health_off@test.com", health_enabled=False)
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(user)
        self.assertEqual(state, {"enabled": False})
        # Critical: no ghost signals like sleep_trend leaking through
        self.assertNotIn("sleep_trend", state)
        self.assertNotIn("weight_trend", state)
        self.assertNotIn("body_fat_trend", state)

    def test_enabled_health_runs_normally(self):
        user = _make_user("health_on@test.com", health_enabled=True)
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(user)
        self.assertEqual(state.get("enabled"), True)


class FinanceStateGateTests(TestCase):
    def test_disabled_finance_returns_enabled_false(self):
        user = _make_user("finance_off@test.com", finances_enabled=False)
        from apps.core.ai_state.state_builder import build_finance_state
        state = build_finance_state(user)
        self.assertEqual(state, {"enabled": False})

    def test_enabled_finance_runs_normally(self):
        user = _make_user("finance_on@test.com", finances_enabled=True)
        from apps.core.ai_state.state_builder import build_finance_state
        state = build_finance_state(user)
        self.assertEqual(state.get("enabled"), True)


# ── Rule gating ──────────────────────────────────────────────────────

class MotivationDriftRuleGateTests(TestCase):
    """MotivationDriftRule must NOT fire on disabled goals / journal —
    previously `goals.get('avg_completion_rate', 1.0)` and
    `goals.get('overdue_goal_count', 0)` would default to "perfect
    progress" and silently suppress the insight, while a declining
    mood alone would still look like motivation drift."""

    def _eval(self, journal_state, goals_state):
        from apps.core.ai_insights.rules_cross_domain import (
            MotivationDriftRule,
        )
        rule = MotivationDriftRule()
        event = {
            "event_type": "scheduled_check",
            "user_state": {
                "journal": journal_state,
                "goals": goals_state,
            },
        }
        user = MagicMock()
        user.id = 1
        return rule.evaluate(user, event)

    def test_bails_when_goals_disabled(self):
        results = self._eval(
            journal_state={"mood_trend": "declining"},
            goals_state={"enabled": False},
        )
        self.assertEqual(results, [])

    def test_bails_when_journal_disabled(self):
        results = self._eval(
            journal_state={"enabled": False},
            goals_state={"avg_completion_rate": 0.2, "overdue_goal_count": 3},
        )
        self.assertEqual(results, [])

    def test_bails_when_avg_completion_rate_missing(self):
        """Don't default to 1.0 and mask missing goal data."""
        results = self._eval(
            journal_state={"mood_trend": "declining"},
            goals_state={"overdue_goal_count": 0},  # no avg_completion_rate
        )
        self.assertEqual(results, [])


class OvertrainingRiskRuleGateTests(TestCase):
    def _eval(self, health_state):
        from apps.core.ai_insights.rules_cross_domain import (
            OvertrainingRiskRule,
        )
        rule = OvertrainingRiskRule()
        event = {
            "event_type": "scheduled_check",
            "user_state": {"health": health_state},
        }
        user = MagicMock()
        user.id = 1
        return rule.evaluate(user, event)

    def test_bails_when_health_disabled(self):
        results = self._eval({"enabled": False})
        self.assertEqual(results, [])

    def test_bails_when_required_inputs_missing(self):
        """No more sleep_avg=8 / workout_count=0 / sleep_trend='stable'
        defaults hiding the missing-data condition."""
        results = self._eval({"enabled": True})
        self.assertEqual(results, [])


class ComplianceRiskRuleGateTests(TestCase):
    def _eval(self, health_state, medicine_state):
        from apps.core.ai_insights.rules_cross_domain import (
            ComplianceRiskRule,
        )
        rule = ComplianceRiskRule()
        event = {
            "event_type": "scheduled_check",
            "user_state": {
                "health": health_state,
                "medicine": medicine_state,
            },
        }
        user = MagicMock()
        user.id = 1
        return rule.evaluate(user, event)

    def test_bails_when_health_disabled(self):
        results = self._eval(
            health_state={"enabled": False},
            medicine_state={"adherence_7d": 40},
        )
        self.assertEqual(results, [])

    def test_bails_when_medicine_disabled(self):
        results = self._eval(
            health_state={"weight_trend": "increasing"},
            medicine_state={"enabled": False},
        )
        self.assertEqual(results, [])


class WorkoutConsistencyRuleGateTests(TestCase):
    def _eval(self, health_state, fitness_state):
        from apps.core.ai_insights.rules_transformation import (
            WorkoutConsistencyRule,
        )
        rule = WorkoutConsistencyRule()
        event = {
            "event_type": "scheduled_check",
            "user_state": {
                "health": health_state,
                "fitness": fitness_state,
            },
        }
        user = MagicMock()
        user.id = 1
        return rule.evaluate(user, event)

    def test_bails_when_health_disabled(self):
        results = self._eval(
            health_state={"enabled": False},
            fitness_state={"workouts_7d": 0},
        )
        self.assertEqual(results, [])


class FastingConsistencyRuleGateTests(TestCase):
    def _eval(self, fasting_state):
        from apps.core.ai_insights.rules_transformation import (
            FastingConsistencyRule,
        )
        rule = FastingConsistencyRule()
        event = {
            "event_type": "scheduled_check",
            "user_state": {"fasting": fasting_state},
        }
        user = MagicMock()
        user.id = 1
        return rule.evaluate(user, event)

    def test_bails_when_fasting_disabled(self):
        results = self._eval({"enabled": False})
        self.assertEqual(results, [])
