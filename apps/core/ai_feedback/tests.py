"""
Phase 4 CoS — Feedback Loop Tests.

Tests for:
- PredictionValidator
- InsightEngagementTracker
- BriefingEngagementTracker
- InterventionEffectivenessTracker
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.core.ai_feedback.briefing_tracker import (
    get_briefing_engagement_profile,
    get_preferred_briefing_length,
    record_briefing_opened,
    record_briefing_time,
)
from apps.core.ai_feedback.insight_tracker import (
    get_insight_engagement_profile,
    get_insight_type_weights,
    record_insight_engagement,
)
from apps.core.ai_feedback.intervention_tracker import (
    get_escalation_speed_modifier,
    get_intervention_effectiveness,
)
from apps.core.ai_feedback.models import (
    BriefingEngagement,
    BriefingEngagementProfile,
    InsightEngagement,
    InsightEngagementProfile,
    InterventionEffectivenessProfile,
    PredictionAccuracyProfile,
    PredictionOutcome,
)
from apps.core.ai_feedback.prediction_validator import (
    get_accuracy_profile,
    get_confidence_adjustment,
)
from apps.core.ai_insights.models import Insight
from apps.core.ai_predictions.models import Prediction
from apps.users.models import User


class PredictionOutcomeModelTest(TestCase):
    """Tests for PredictionOutcome and PredictionAccuracyProfile models."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="feedback@test.com", password="testpass123"
        )

    def test_prediction_outcome_creation(self):
        prediction = Prediction.objects.create(
            user=self.user,
            prediction_type="weight_30d",
            module="health",
            predicted_value=180.0,
            predicted_date=timezone.now() - timedelta(days=1),
            confidence_score=0.8,
            explanation="Test prediction",
            dedupe_key="test_dedupe_1",
        )
        outcome = PredictionOutcome.objects.create(
            prediction=prediction,
            user=self.user,
            actual_value=182.0,
            error_abs=2.0,
            error_pct=1.1,
            accuracy_score=0.989,
        )
        self.assertEqual(outcome.prediction, prediction)
        self.assertAlmostEqual(outcome.accuracy_score, 0.989)

    def test_accuracy_profile_creation(self):
        profile = PredictionAccuracyProfile.objects.create(
            user=self.user,
            prediction_type="weight_30d",
            total_validated=10,
            total_accurate=8,
            avg_accuracy=0.85,
        )
        self.assertEqual(profile.prediction_type, "weight_30d")
        self.assertEqual(profile.total_validated, 10)

    def test_get_accuracy_profile(self):
        profile = get_accuracy_profile(self.user, "weight_30d")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.prediction_type, "weight_30d")

    def test_confidence_adjustment_insufficient_data(self):
        adj = get_confidence_adjustment(self.user, "weight_30d")
        self.assertEqual(adj, 0.0)

    def test_confidence_adjustment_with_data(self):
        PredictionAccuracyProfile.objects.create(
            user=self.user,
            prediction_type="weight_30d",
            total_validated=5,
            avg_accuracy=0.85,
            confidence_adjustment=0.1,
        )
        adj = get_confidence_adjustment(self.user, "weight_30d")
        self.assertEqual(adj, 0.1)


class InsightEngagementTest(TestCase):
    """Tests for InsightEngagementTracker."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="insight@test.com", password="testpass123"
        )
        self.insight = Insight.objects.create(
            user=self.user,
            module="health",
            insight_type="weight_trend_up",
            severity="warning",
            title="Weight trending up",
            message="Your weight has been increasing.",
            confidence_score=0.8,
            explain_why="3 consecutive increases",
            dedupe_key="test_insight_1",
        )

    def test_record_viewed(self):
        engagement = record_insight_engagement(self.user, self.insight, "viewed")
        self.assertEqual(engagement.event_type, "viewed")
        self.insight.refresh_from_db()
        self.assertEqual(self.insight.status, "read")

    def test_record_dismissed(self):
        engagement = record_insight_engagement(self.user, self.insight, "dismissed")
        self.assertEqual(engagement.event_type, "dismissed")
        self.insight.refresh_from_db()
        self.assertEqual(self.insight.status, "dismissed")

    def test_record_acted(self):
        engagement = record_insight_engagement(self.user, self.insight, "acted")
        self.assertEqual(engagement.event_type, "acted")

    def test_engagement_profile_update(self):
        record_insight_engagement(self.user, self.insight, "viewed")
        profile = get_insight_engagement_profile(self.user)
        self.assertEqual(profile.total_viewed, 1)
        self.assertGreater(profile.engagement_score, 0)

    def test_insight_type_weights(self):
        record_insight_engagement(self.user, self.insight, "acted")
        weights = get_insight_type_weights(self.user)
        self.assertIn("weight_trend_up", weights)
        self.assertGreater(weights["weight_trend_up"], 1.0)

    def test_dismissed_lowers_weight(self):
        record_insight_engagement(self.user, self.insight, "dismissed")
        weights = get_insight_type_weights(self.user)
        if "weight_trend_up" in weights:
            self.assertLess(weights["weight_trend_up"], 1.0)


class BriefingEngagementTest(TestCase):
    """Tests for BriefingEngagementTracker."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="briefing@test.com", password="testpass123"
        )

    def test_record_briefing_opened(self):
        engagement = record_briefing_opened(
            self.user, "daily_briefing", 1
        )
        self.assertEqual(engagement.content_type, "daily_briefing")
        self.assertEqual(engagement.content_id, 1)

    def test_record_briefing_time(self):
        engagement = record_briefing_opened(
            self.user, "daily_briefing", 1
        )
        record_briefing_time(self.user, engagement.id, 45, scrolled_to_end=True)
        engagement.refresh_from_db()
        self.assertEqual(engagement.time_spent_seconds, 45)
        self.assertTrue(engagement.scrolled_to_end)

    def test_preferred_length_default(self):
        length = get_preferred_briefing_length(self.user)
        self.assertEqual(length, "standard")

    def test_engagement_profile(self):
        record_briefing_opened(self.user, "daily_briefing", 1)
        profile = get_briefing_engagement_profile(self.user)
        self.assertEqual(profile.total_briefings_opened, 1)


class InterventionEffectivenessTest(TestCase):
    """Tests for InterventionEffectivenessTracker."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="intervention@test.com", password="testpass123"
        )

    def test_get_effectiveness_default(self):
        profile = get_intervention_effectiveness(self.user)
        self.assertEqual(profile.effectiveness_score, 0.5)

    def test_escalation_modifier_default(self):
        modifier = get_escalation_speed_modifier(self.user)
        self.assertEqual(modifier, 0.0)

    def test_effectiveness_profile_creation(self):
        profile = InterventionEffectivenessProfile.objects.create(
            user=self.user,
            total_interventions=10,
            total_accepted=7,
            total_dismissed=2,
            total_drift_resolved=5,
            effectiveness_score=0.75,
            escalation_speed_modifier=-0.3,
        )
        self.assertEqual(profile.total_interventions, 10)
        self.assertEqual(profile.escalation_speed_modifier, -0.3)

    def test_escalation_modifier_responsive_user(self):
        InterventionEffectivenessProfile.objects.create(
            user=self.user,
            total_interventions=5,
            effectiveness_score=0.8,
            escalation_speed_modifier=-0.3,
        )
        modifier = get_escalation_speed_modifier(self.user)
        self.assertEqual(modifier, -0.3)
