"""
Tests for the deterministic health coaching layer.

The coaching engine is a pure function inside HealthTrendAnalyzer._build_coaching.
It selects ONE primary constraint, produces deterministic actions, and optionally
includes reinforcement from strengths. No LLM calls. No DB writes.

Covers:
1. Sleep deficit → sleep as primary constraint
2. Good sleep, low movement → activity as constraint
3. Positive signals only → reinforcement, no constraint
4. Multiple signals → highest-priority domain wins
5. Weakness-only detection (no risk_flags)
6. Coaching output structure validation
7. Integration: coaching flows through to CoS context
"""
from django.test import TestCase

from apps.health.services.trend_analyzer import HealthTrendAnalyzer


class TestCoachingConstraintSelection(TestCase):
    """_build_coaching selects the correct primary constraint."""

    def test_sleep_deficit_wins_over_lower_priority(self):
        """Sleep warning beats workout and activity warnings."""
        risk_flags = [
            {"domain": "workout", "severity": "warning", "message": "Workout freq dropped"},
            {"domain": "sleep", "severity": "warning", "message": "Sleep debt: 4/7 nights below 7h"},
            {"domain": "activity", "severity": "info", "message": "Steps declining"},
        ]
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=risk_flags,
            weaknesses=[],
            strengths=["Strong protein intake"],
            trends={},
            rolling_7d={},
        )
        self.assertEqual(coaching["primary_constraint"], "sleep")
        self.assertIn("sleep", coaching["insight"].lower())
        self.assertIsNotNone(coaching["primary_action"])
        self.assertEqual(coaching["reinforcement"], "Strong protein intake")

    def test_good_sleep_low_movement(self):
        """With sleep fine, activity warning becomes primary."""
        risk_flags = [
            {"domain": "activity", "severity": "warning", "message": "Low daily steps"},
        ]
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=risk_flags,
            weaknesses=[],
            strengths=["Good sleep average (7.2h)"],
            trends={},
            rolling_7d={},
        )
        self.assertEqual(coaching["primary_constraint"], "activity")
        self.assertIn("movement", coaching["insight"].lower())

    def test_positive_signals_only_reinforcement(self):
        """No risk_flags or weaknesses → reinforcement mode, no constraint."""
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=[],
            strengths=["Healthy weight loss pace (1.2 lbs/week)", "Strong protein intake"],
            trends={},
            rolling_7d={},
        )
        self.assertIsNone(coaching["primary_constraint"])
        self.assertIsNone(coaching["primary_action"])
        self.assertEqual(coaching["reinforcement"], "Healthy weight loss pace (1.2 lbs/week)")

    def test_no_data_at_all(self):
        """No signals at all → basic tracking message."""
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=[],
            strengths=[],
            trends={},
            rolling_7d={},
        )
        self.assertIsNone(coaching["primary_constraint"])
        self.assertIsNone(coaching["primary_action"])
        self.assertIsNone(coaching["reinforcement"])
        self.assertIn("tracking", coaching["insight"].lower())

    def test_medication_warning_beats_info_flags(self):
        """Warning-severity medication flag beats info-severity sleep flag."""
        risk_flags = [
            {"domain": "sleep", "severity": "info", "message": "Slightly inconsistent"},
            {"domain": "medication", "severity": "warning", "message": "Low adherence 60%"},
        ]
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=risk_flags,
            weaknesses=[],
            strengths=[],
            trends={},
            rolling_7d={},
        )
        self.assertEqual(coaching["primary_constraint"], "medication")

    def test_multiple_warnings_highest_priority_wins(self):
        """With multiple warning-level flags, domain priority order decides."""
        risk_flags = [
            {"domain": "protein", "severity": "warning", "message": "Low protein"},
            {"domain": "glucose", "severity": "warning", "message": "Glucose rising"},
            {"domain": "sleep", "severity": "warning", "message": "Sleep debt"},
        ]
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=risk_flags,
            weaknesses=[],
            strengths=[],
            trends={},
            rolling_7d={},
        )
        # Sleep is tier 1, glucose is tier 2, protein is tier 2
        self.assertEqual(coaching["primary_constraint"], "sleep")

    def test_glucose_beats_protein_at_same_severity(self):
        """At warning severity, glucose comes before protein in priority."""
        risk_flags = [
            {"domain": "protein", "severity": "warning", "message": "Low protein"},
            {"domain": "glucose", "severity": "warning", "message": "Glucose rising"},
        ]
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=risk_flags,
            weaknesses=[],
            strengths=[],
            trends={},
            rolling_7d={},
        )
        self.assertEqual(coaching["primary_constraint"], "glucose")


class TestCoachingFromWeaknesses(TestCase):
    """Constraint selection falls back to weaknesses when no risk_flags match."""

    def test_weakness_only_sleep(self):
        """Sleep weakness detected from weakness string (no risk_flag)."""
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=["Averaging 6.2h sleep (target: 7-8h)"],
            strengths=[],
            trends={},
            rolling_7d={},
        )
        self.assertEqual(coaching["primary_constraint"], "sleep")

    def test_weakness_only_protein(self):
        """Protein weakness detected from weakness string."""
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=["Below protein target (120g/day, 65% of 185g)"],
            strengths=[],
            trends={},
            rolling_7d={},
        )
        self.assertEqual(coaching["primary_constraint"], "protein")

    def test_weakness_only_workout(self):
        """Workout weakness detected from string containing 'training volume'."""
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=["Training volume declining (-20%)"],
            strengths=[],
            trends={},
            rolling_7d={},
        )
        self.assertEqual(coaching["primary_constraint"], "workout")


class TestCoachingOutputStructure(TestCase):
    """Coaching output has all required fields and correct types."""

    def test_constraint_output_has_all_fields(self):
        """When a constraint exists, all fields are populated."""
        risk_flags = [
            {"domain": "sleep", "severity": "warning", "message": "Sleep debt pattern"},
        ]
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=risk_flags,
            weaknesses=[],
            strengths=["Strong workout frequency"],
            trends={},
            rolling_7d={},
        )
        self.assertIn("primary_constraint", coaching)
        self.assertIn("insight", coaching)
        self.assertIn("primary_action", coaching)
        self.assertIn("secondary_action", coaching)
        self.assertIn("reinforcement", coaching)
        self.assertIn("supporting_signals", coaching)

        self.assertIsInstance(coaching["primary_constraint"], str)
        self.assertIsInstance(coaching["insight"], str)
        self.assertIsInstance(coaching["primary_action"], str)
        self.assertIsInstance(coaching["supporting_signals"], list)

    def test_reinforcement_output_has_null_actions(self):
        """In reinforcement mode, actions are None."""
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=[],
            strengths=["Good sleep"],
            trends={},
            rolling_7d={},
        )
        self.assertIsNone(coaching["primary_constraint"])
        self.assertIsNone(coaching["primary_action"])
        self.assertIsNone(coaching["secondary_action"])

    def test_supporting_signals_excludes_primary(self):
        """Supporting signals list does not include the primary constraint."""
        risk_flags = [
            {"domain": "sleep", "severity": "warning", "message": "Sleep debt"},
            {"domain": "protein", "severity": "warning", "message": "Low protein"},
            {"domain": "activity", "severity": "info", "message": "Steps down"},
        ]
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=risk_flags,
            weaknesses=[],
            strengths=[],
            trends={},
            rolling_7d={},
        )
        self.assertEqual(coaching["primary_constraint"], "sleep")
        self.assertNotIn("sleep", coaching["supporting_signals"])
        self.assertIn("protein", coaching["supporting_signals"])

    def test_max_two_actions(self):
        """Every domain produces at most 2 actions."""
        for domain in HealthTrendAnalyzer._COACHING_ACTIONS:
            actions = HealthTrendAnalyzer._COACHING_ACTIONS[domain]
            self.assertIsInstance(actions, tuple)
            self.assertEqual(len(actions), 2)
            self.assertIsInstance(actions[0], str)  # primary always present
            # secondary may be None

    def test_every_domain_has_insight_template(self):
        """Every domain in the action map also has an insight template."""
        for domain in HealthTrendAnalyzer._COACHING_ACTIONS:
            self.assertIn(
                domain, HealthTrendAnalyzer._CONSTRAINT_INSIGHTS,
                f"Domain '{domain}' has actions but no insight template",
            )


class TestCoachingIntegration(TestCase):
    """Coaching output flows through HealthTrendAnalyzer.analyze()."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.conf import settings
        from apps.users.models import TermsAcceptance

        User = get_user_model()
        self.user = User.objects.create_user(
            email="coach@example.com", password="testpass123",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_analyze_returns_coaching_dict(self):
        """HealthTrendAnalyzer.analyze() includes a coaching dict in results."""
        from django.utils import timezone

        result = HealthTrendAnalyzer.analyze(self.user, timezone.localdate())
        self.assertIn("coaching", result)
        coaching = result["coaching"]
        self.assertIn("primary_constraint", coaching)
        self.assertIn("insight", coaching)
        self.assertIn("primary_action", coaching)

    def test_top_recommendation_matches_coaching_insight(self):
        """top_recommendation is populated from coaching.insight for backward compat."""
        from django.utils import timezone

        result = HealthTrendAnalyzer.analyze(self.user, timezone.localdate())
        coaching = result["coaching"]
        self.assertEqual(result["top_recommendation"], coaching["insight"])
