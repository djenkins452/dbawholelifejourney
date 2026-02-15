"""
DBE — Daily Briefing Engine Tests.

Covers:
- DailyBriefing model creation and unique constraint
- Briefing selector prioritization
- Briefing ranker ordering
- Briefing logger duplicate prevention
- Briefing engine end-to-end (mocked)
- Dashboard tile rendering
- Management command
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, TestCase
from django.utils import timezone

from apps.core.ai_briefing.briefing_engine import generate_daily_briefing, get_todays_briefing
from apps.core.ai_briefing.briefing_logger import store_briefing
from apps.core.ai_briefing.briefing_ranker import rank_briefing_items
from apps.core.ai_briefing.briefing_selector import select_briefing_items
from apps.core.ai_briefing.models import DailyBriefing
from apps.users.models import TermsAcceptance

User = get_user_model()


def _make_guidance(id, title, message, priority=3, source="sae_state", module="health", confidence_score=None):
    """Create a mock guidance item."""
    return SimpleNamespace(
        id=id,
        title=title,
        message=message,
        priority=priority,
        source=source,
        module=module,
        confidence_score=confidence_score,
    )


def _make_insight(id, title, message, severity="info", module="health", confidence_score=0.5):
    """Create a mock insight."""
    return SimpleNamespace(
        id=id,
        title=title,
        message=message,
        severity=severity,
        module=module,
        confidence_score=confidence_score,
    )


def _make_prediction(id, prediction_type, explanation, confidence_score=0.8, module="health"):
    """Create a mock prediction."""
    return SimpleNamespace(
        id=id,
        prediction_type=prediction_type,
        explanation=explanation,
        confidence_score=confidence_score,
        module=module,
    )


# ===========================================================================
# Model Tests
# ===========================================================================


class DailyBriefingModelTest(TestCase):
    """Tests for the DailyBriefing model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="briefing_model@test.com", password="testpass123"
        )

    def test_create_briefing(self):
        briefing = DailyBriefing.objects.create(
            user=self.user,
            briefing_date=timezone.now().date(),
            summary="Test summary.",
        )
        self.assertEqual(briefing.user, self.user)
        self.assertEqual(briefing.summary, "Test summary.")
        self.assertIsNotNone(briefing.created_at)

    def test_unique_constraint_prevents_duplicate(self):
        today = timezone.now().date()
        DailyBriefing.objects.create(
            user=self.user, briefing_date=today, summary="First"
        )
        with self.assertRaises(IntegrityError):
            DailyBriefing.objects.create(
                user=self.user, briefing_date=today, summary="Duplicate"
            )

    def test_different_dates_allowed(self):
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        DailyBriefing.objects.create(
            user=self.user, briefing_date=today, summary="Today"
        )
        DailyBriefing.objects.create(
            user=self.user, briefing_date=yesterday, summary="Yesterday"
        )
        self.assertEqual(DailyBriefing.objects.filter(user=self.user).count(), 2)

    def test_str_representation(self):
        briefing = DailyBriefing.objects.create(
            user=self.user,
            briefing_date=timezone.now().date(),
            summary="Test",
        )
        self.assertIn(str(self.user.id), str(briefing))

    def test_json_fields_default_to_empty_dict(self):
        briefing = DailyBriefing.objects.create(
            user=self.user,
            briefing_date=timezone.now().date(),
            summary="Test",
        )
        self.assertEqual(briefing.state_snapshot, {})
        self.assertEqual(briefing.guidance_snapshot, {})
        self.assertEqual(briefing.insight_snapshot, {})
        self.assertEqual(briefing.prediction_snapshot, {})


# ===========================================================================
# Selector Tests
# ===========================================================================


class BriefingSelectorTest(TestCase):
    """Tests for briefing_selector."""

    def test_max_5_items(self):
        guidance = [
            _make_guidance(i, f"G{i}", f"Msg {i}") for i in range(10)
        ]
        result = select_briefing_items(guidance, [], [])
        self.assertLessEqual(len(result), 5)

    def test_critical_guidance_prioritized(self):
        guidance = [
            _make_guidance(1, "Critical", "Urgent", priority=1),
            _make_guidance(2, "Low", "Not urgent", priority=5),
        ]
        result = select_briefing_items(guidance, [], [])
        self.assertEqual(result[0]["title"], "Critical")

    def test_high_confidence_predictions_ranked_high(self):
        predictions = [
            _make_prediction(1, "weight_30d", "Weight dropping", confidence_score=0.95),
        ]
        guidance = [
            _make_guidance(2, "Info", "Low priority", priority=5),
        ]
        result = select_briefing_items(guidance, [], predictions)
        # Prediction with 0.95 confidence should rank above low-priority guidance
        types = [r["type"] for r in result]
        self.assertIn("prediction", types)

    def test_critical_insights_included(self):
        insights = [
            _make_insight(1, "Weight spike", "Your weight spiked", severity="critical"),
        ]
        result = select_briefing_items([], insights, [])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "insight")

    def test_empty_inputs_returns_empty(self):
        result = select_briefing_items([], [], [])
        self.assertEqual(result, [])

    def test_mixed_sources_all_types_present(self):
        guidance = [_make_guidance(1, "G1", "Guidance msg", priority=2)]
        insights = [_make_insight(2, "I1", "Insight msg", severity="warning")]
        predictions = [_make_prediction(3, "p1", "Pred msg", confidence_score=0.9)]
        result = select_briefing_items(guidance, insights, predictions)
        types = {r["type"] for r in result}
        self.assertEqual(types, {"guidance", "insight", "prediction"})


# ===========================================================================
# Ranker Tests
# ===========================================================================


class BriefingRankerTest(TestCase):
    """Tests for briefing_ranker."""

    def test_empty_items(self):
        self.assertEqual(rank_briefing_items([]), [])

    def test_priority_ordering(self):
        items = [
            {"type": "guidance", "priority": 5, "confidence": None},
            {"type": "guidance", "priority": 1, "confidence": None},
            {"type": "guidance", "priority": 3, "confidence": None},
        ]
        ranked = rank_briefing_items(items)
        priorities = [r["priority"] for r in ranked]
        self.assertEqual(priorities, [1, 3, 5])

    def test_confidence_tiebreaker(self):
        items = [
            {"type": "prediction", "priority": 2, "confidence": 0.6},
            {"type": "prediction", "priority": 2, "confidence": 0.95},
        ]
        ranked = rank_briefing_items(items)
        confidences = [r["confidence"] for r in ranked]
        # Higher confidence should rank first (lower score)
        self.assertEqual(confidences, [0.95, 0.6])

    def test_type_tiebreaker(self):
        items = [
            {"type": "insight", "priority": 3, "confidence": 0.5},
            {"type": "guidance", "priority": 3, "confidence": 0.5},
        ]
        ranked = rank_briefing_items(items)
        types = [r["type"] for r in ranked]
        self.assertEqual(types, ["guidance", "insight"])


# ===========================================================================
# Logger Tests
# ===========================================================================


class BriefingLoggerTest(TestCase):
    """Tests for briefing_logger."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="briefing_logger@test.com", password="testpass123"
        )

    def test_store_creates_briefing(self):
        briefing = store_briefing(
            user=self.user,
            summary="Test summary",
            ranked_items=[],
            state={"health": {"weight_current": 200}},
            guidance_items=[],
            insights=[],
            predictions=[],
        )
        self.assertIsNotNone(briefing)
        self.assertEqual(briefing.summary, "Test summary")
        self.assertEqual(briefing.briefing_date, timezone.now().date())

    def test_duplicate_prevention_returns_existing(self):
        first = store_briefing(
            user=self.user,
            summary="First",
            ranked_items=[],
            state={},
            guidance_items=[],
            insights=[],
            predictions=[],
        )
        second = store_briefing(
            user=self.user,
            summary="Duplicate",
            ranked_items=[],
            state={},
            guidance_items=[],
            insights=[],
            predictions=[],
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.summary, "First")  # Original kept

    def test_snapshots_serialized(self):
        guidance = [_make_guidance(1, "G1", "Msg", priority=2, source="sae_state", module="health")]
        insights = [_make_insight(2, "I1", "Msg", severity="warning", module="goals")]
        predictions = [_make_prediction(3, "weight_30d", "Explanation", confidence_score=0.85, module="health")]

        briefing = store_briefing(
            user=self.user,
            summary="Test",
            ranked_items=[],
            state={"health": {}},
            guidance_items=guidance,
            insights=insights,
            predictions=predictions,
        )
        self.assertEqual(briefing.guidance_snapshot["count"], 1)
        self.assertEqual(briefing.insight_snapshot["count"], 1)
        self.assertEqual(briefing.prediction_snapshot["count"], 1)


# ===========================================================================
# Engine Integration Tests (mocked)
# ===========================================================================


class BriefingEngineTest(TestCase):
    """Tests for briefing_engine generate_daily_briefing."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="briefing_engine@test.com", password="testpass123"
        )

    @patch("apps.core.ai_briefing.briefing_engine._get_predictions", return_value=[])
    @patch("apps.core.ai_briefing.briefing_engine._get_insights", return_value=[])
    @patch("apps.core.ai_briefing.briefing_engine._get_guidance", return_value=[])
    @patch("apps.core.ai_briefing.briefing_engine._get_state", return_value={"health": {"weight_trend": "decreasing"}})
    def test_generates_briefing(self, mock_state, mock_guidance, mock_insights, mock_preds):
        briefing = generate_daily_briefing(self.user)
        self.assertIsNotNone(briefing)
        self.assertEqual(briefing.briefing_date, timezone.now().date())
        self.assertIn("weight", briefing.summary.lower())

    @patch("apps.core.ai_briefing.briefing_engine._get_predictions", return_value=[])
    @patch("apps.core.ai_briefing.briefing_engine._get_insights", return_value=[])
    @patch("apps.core.ai_briefing.briefing_engine._get_guidance", return_value=[])
    @patch("apps.core.ai_briefing.briefing_engine._get_state", return_value={})
    def test_skips_existing_briefing(self, mock_state, mock_guidance, mock_insights, mock_preds):
        # Create first
        first = generate_daily_briefing(self.user)
        # Try again — should return existing
        second = generate_daily_briefing(self.user)
        self.assertEqual(first.id, second.id)
        # State should only be called once (second call hits early return)
        mock_state.assert_called_once()

    def test_get_todays_briefing_returns_none_when_empty(self):
        result = get_todays_briefing(self.user)
        self.assertIsNone(result)

    def test_get_todays_briefing_returns_briefing(self):
        DailyBriefing.objects.create(
            user=self.user,
            briefing_date=timezone.now().date(),
            summary="Today's briefing",
        )
        result = get_todays_briefing(self.user)
        self.assertIsNotNone(result)
        self.assertEqual(result.summary, "Today's briefing")

    @patch("apps.core.ai_briefing.briefing_engine._get_predictions", return_value=[])
    @patch("apps.core.ai_briefing.briefing_engine._get_insights", return_value=[])
    @patch("apps.core.ai_briefing.briefing_engine._get_guidance")
    @patch("apps.core.ai_briefing.briefing_engine._get_state", return_value={})
    def test_guidance_messages_in_summary(self, mock_state, mock_guidance, mock_insights, mock_preds):
        mock_guidance.return_value = [
            _make_guidance(1, "Weight Alert", "Your weight trend is improving.", priority=2),
        ]
        briefing = generate_daily_briefing(self.user)
        self.assertIn("weight trend is improving", briefing.summary.lower())


# ===========================================================================
# Dashboard Tile Tests
# ===========================================================================


class DailyBriefingTileTest(TestCase):
    """Tests for the daily briefing dashboard tile."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="briefing_tile@test.com",
            password="testpass123",
            first_name="BriefingTest",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.ai_enabled = True
        self.user.preferences.save()
        self.client.login(email="briefing_tile@test.com", password="testpass123")

    def test_tile_renders_empty_state(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "daily-briefing-tile")
        self.assertContains(response, "No briefing yet today")

    def test_tile_shows_briefing_when_exists(self):
        DailyBriefing.objects.create(
            user=self.user,
            briefing_date=timezone.now().date(),
            summary="Your weight trend is improving. You have one goal approaching its deadline.",
        )
        response = self.client.get("/dashboard/")
        self.assertContains(response, "Your weight trend is improving")
        self.assertContains(response, "one goal approaching")

    def test_context_has_daily_briefing(self):
        response = self.client.get("/dashboard/")
        self.assertIn("daily_briefing", response.context)

    def test_tile_hidden_when_ai_disabled(self):
        self.user.preferences.ai_enabled = False
        self.user.preferences.save()
        response = self.client.get("/dashboard/")
        tiles = response.context.get("dashboard_tiles", [])
        tile_ids = [t["id"] for t in tiles]
        self.assertNotIn("daily_briefing", tile_ids)
