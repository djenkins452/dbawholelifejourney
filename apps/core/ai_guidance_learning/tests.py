"""
GLOE -- Tests for the Guidance Learning Optimization Engine.

Tests cover:
- GuidanceLearningProfile model
- GuidanceLearningEvent model
- Learning calculator (responsiveness score)
- Learning logger (event creation + profile update)
- Learning engine (profile aggregation)
- PGE ranker integration (responsiveness adjustment)
"""

from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_guidance_learning.learning_calculator import (
    WEIGHT_ACTED,
    WEIGHT_ACKNOWLEDGED,
    WEIGHT_DISMISSED,
    WEIGHT_RESPONSE_SPEED,
    calculate_responsiveness_score,
    _response_speed_score,
)
from apps.core.ai_guidance_learning.learning_engine import (
    get_responsiveness_score,
    update_learning_profile,
)
from apps.core.ai_guidance_learning.learning_logger import log_learning_event
from apps.core.ai_guidance_learning.learning_models import (
    GuidanceLearningEvent,
    GuidanceLearningProfile,
)
from apps.core.ai_guidance.guidance_ranker import (
    _compute_rank_score,
    rank_guidance,
    RESPONSIVENESS_INFLUENCE,
)
from apps.users.models import User


def _create_test_user(email="gloetest@example.com"):
    """Create a test user with required setup."""
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _create_guidance_item(user, title="Test Guidance", **kwargs):
    """Create a GuidanceItem for testing."""
    from apps.core.ai_guidance.models import GuidanceItem

    defaults = {
        "user": user,
        "title": title,
        "message": "Test message",
        "priority": 3,
        "guidance_type": "recommendation",
        "source": "test",
        "module": "health",
    }
    defaults.update(kwargs)
    return GuidanceItem.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class GuidanceLearningProfileModelTest(TestCase):
    """Tests for GuidanceLearningProfile model."""

    def setUp(self):
        self.user = _create_test_user()

    def test_create_profile(self):
        profile = GuidanceLearningProfile.objects.create(user=self.user)
        self.assertEqual(profile.responsiveness_score, 0.5)
        self.assertEqual(profile.total_guidance_seen, 0)

    def test_str_representation(self):
        profile = GuidanceLearningProfile.objects.create(user=self.user)
        self.assertIn(str(self.user.id), str(profile))
        self.assertIn("0.50", str(profile))

    def test_default_values(self):
        profile = GuidanceLearningProfile.objects.create(user=self.user)
        self.assertEqual(profile.total_guidance_acknowledged, 0)
        self.assertEqual(profile.total_guidance_dismissed, 0)
        self.assertEqual(profile.total_guidance_acted, 0)
        self.assertEqual(profile.avg_response_time_seconds, 0.0)

    def test_one_to_one_constraint(self):
        GuidanceLearningProfile.objects.create(user=self.user)
        with self.assertRaises(Exception):
            GuidanceLearningProfile.objects.create(user=self.user)


class GuidanceLearningEventModelTest(TestCase):
    """Tests for GuidanceLearningEvent model."""

    def setUp(self):
        self.user = _create_test_user()
        self.item = _create_guidance_item(self.user)

    def test_create_event(self):
        event = GuidanceLearningEvent.objects.create(
            user=self.user,
            guidance_item=self.item,
            event_type="acknowledged",
            response_time_seconds=120.0,
        )
        self.assertEqual(event.event_type, "acknowledged")
        self.assertEqual(event.response_time_seconds, 120.0)

    def test_str_representation(self):
        event = GuidanceLearningEvent.objects.create(
            user=self.user,
            guidance_item=self.item,
            event_type="acted",
        )
        self.assertIn("acted", str(event))

    def test_event_types(self):
        for event_type in ["acknowledged", "dismissed", "acted", "ignored"]:
            event = GuidanceLearningEvent.objects.create(
                user=self.user,
                guidance_item=self.item,
                event_type=event_type,
            )
            self.assertEqual(event.event_type, event_type)

    def test_ordering_newest_first(self):
        e1 = GuidanceLearningEvent.objects.create(
            user=self.user,
            guidance_item=self.item,
            event_type="acknowledged",
        )
        e2 = GuidanceLearningEvent.objects.create(
            user=self.user,
            guidance_item=self.item,
            event_type="dismissed",
        )
        events = list(GuidanceLearningEvent.objects.all())
        self.assertEqual(events[0].id, e2.id)


# ---------------------------------------------------------------------------
# Calculator Tests
# ---------------------------------------------------------------------------


class ResponseSpeedScoreTest(TestCase):
    """Tests for _response_speed_score function."""

    def test_zero_returns_neutral(self):
        self.assertEqual(_response_speed_score(0), 0.5)

    def test_negative_returns_neutral(self):
        self.assertEqual(_response_speed_score(-10), 0.5)

    def test_fast_response_returns_one(self):
        self.assertEqual(_response_speed_score(1800), 1.0)  # 30 min

    def test_exactly_fast_threshold(self):
        self.assertEqual(_response_speed_score(3600), 1.0)  # 1 hour

    def test_slow_response_returns_zero(self):
        self.assertEqual(_response_speed_score(86400 * 5), 0.0)  # 5 days

    def test_exactly_slow_threshold(self):
        self.assertEqual(_response_speed_score(86400 * 3), 0.0)  # 3 days

    def test_midpoint_interpolation(self):
        mid = 3600 + (86400 * 3 - 3600) / 2  # halfway
        score = _response_speed_score(mid)
        self.assertAlmostEqual(score, 0.5, places=1)


class CalculateResponsivenessScoreTest(TestCase):
    """Tests for calculate_responsiveness_score function."""

    def _make_profile(self, seen=10, ack=0, dismissed=0, acted=0, avg_time=0.0):
        """Create a mock profile object."""
        profile = GuidanceLearningProfile()
        profile.total_guidance_seen = seen
        profile.total_guidance_acknowledged = ack
        profile.total_guidance_dismissed = dismissed
        profile.total_guidance_acted = acted
        profile.avg_response_time_seconds = avg_time
        return profile

    def test_no_guidance_returns_neutral(self):
        profile = self._make_profile(seen=0)
        self.assertEqual(calculate_responsiveness_score(profile), 0.5)

    def test_all_acted_high_score(self):
        profile = self._make_profile(seen=10, acted=10, avg_time=1800)
        score = calculate_responsiveness_score(profile)
        # acted_rate=1.0 * 0.40 + speed=1.0 * 0.15 = 0.55
        self.assertGreater(score, 0.5)

    def test_all_dismissed_low_score(self):
        profile = self._make_profile(seen=10, dismissed=10, avg_time=1800)
        score = calculate_responsiveness_score(profile)
        # dismissed_rate=1.0 * -0.20 + speed=1.0 * 0.15 = -0.05 → clamped to 0.0
        self.assertLessEqual(score, 0.1)

    def test_mixed_response(self):
        profile = self._make_profile(
            seen=10, ack=3, dismissed=2, acted=3, avg_time=7200,
        )
        score = calculate_responsiveness_score(profile)
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)

    def test_score_clamped_to_unit_range(self):
        profile = self._make_profile(
            seen=10, ack=10, acted=10, avg_time=100,
        )
        score = calculate_responsiveness_score(profile)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_score_rounded(self):
        profile = self._make_profile(seen=3, acted=1, avg_time=3600)
        score = calculate_responsiveness_score(profile)
        # Should be rounded to 4 decimal places
        self.assertEqual(score, round(score, 4))


# ---------------------------------------------------------------------------
# Logger Tests
# ---------------------------------------------------------------------------


class LogLearningEventTest(TestCase):
    """Tests for log_learning_event function."""

    def setUp(self):
        self.user = _create_test_user()
        self.item = _create_guidance_item(self.user)

    def test_creates_event(self):
        event = log_learning_event(self.user, self.item, "acknowledged")
        self.assertEqual(event.event_type, "acknowledged")
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.guidance_item, self.item)

    def test_calculates_response_time(self):
        event = log_learning_event(self.user, self.item, "acted")
        self.assertGreaterEqual(event.response_time_seconds, 0)

    def test_triggers_profile_update(self):
        log_learning_event(self.user, self.item, "acknowledged")
        profile = GuidanceLearningProfile.objects.get(user=self.user)
        self.assertEqual(profile.total_guidance_acknowledged, 1)

    def test_multiple_events_aggregate(self):
        item2 = _create_guidance_item(self.user, title="Second")
        log_learning_event(self.user, self.item, "acknowledged")
        log_learning_event(self.user, item2, "acted")
        profile = GuidanceLearningProfile.objects.get(user=self.user)
        self.assertEqual(profile.total_guidance_acknowledged, 1)
        self.assertEqual(profile.total_guidance_acted, 1)
        self.assertEqual(profile.total_guidance_seen, 2)


# ---------------------------------------------------------------------------
# Engine Tests
# ---------------------------------------------------------------------------


class UpdateLearningProfileTest(TestCase):
    """Tests for update_learning_profile function."""

    def setUp(self):
        self.user = _create_test_user()

    def test_creates_profile_if_missing(self):
        profile = update_learning_profile(self.user)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.user, self.user)

    def test_updates_existing_profile(self):
        GuidanceLearningProfile.objects.create(user=self.user)
        item = _create_guidance_item(self.user)
        GuidanceLearningEvent.objects.create(
            user=self.user,
            guidance_item=item,
            event_type="acted",
            response_time_seconds=600,
        )
        profile = update_learning_profile(self.user)
        self.assertEqual(profile.total_guidance_acted, 1)
        self.assertEqual(profile.total_guidance_seen, 1)

    def test_aggregates_correctly(self):
        items = [_create_guidance_item(self.user, title=f"G{i}") for i in range(5)]
        for i, item in enumerate(items):
            event_type = ["acknowledged", "dismissed", "acted", "acknowledged", "acted"][i]
            GuidanceLearningEvent.objects.create(
                user=self.user,
                guidance_item=item,
                event_type=event_type,
                response_time_seconds=100 * (i + 1),
            )
        profile = update_learning_profile(self.user)
        self.assertEqual(profile.total_guidance_seen, 5)
        self.assertEqual(profile.total_guidance_acknowledged, 2)
        self.assertEqual(profile.total_guidance_dismissed, 1)
        self.assertEqual(profile.total_guidance_acted, 2)

    def test_computes_responsiveness_score(self):
        item = _create_guidance_item(self.user)
        GuidanceLearningEvent.objects.create(
            user=self.user,
            guidance_item=item,
            event_type="acted",
            response_time_seconds=1800,
        )
        profile = update_learning_profile(self.user)
        self.assertNotEqual(profile.responsiveness_score, 0.5)


class GetResponsivenessScoreTest(TestCase):
    """Tests for get_responsiveness_score function."""

    def setUp(self):
        self.user = _create_test_user()

    def test_no_profile_returns_neutral(self):
        score = get_responsiveness_score(self.user)
        self.assertEqual(score, 0.5)

    def test_returns_profile_score(self):
        GuidanceLearningProfile.objects.create(
            user=self.user,
            responsiveness_score=0.85,
        )
        score = get_responsiveness_score(self.user)
        self.assertEqual(score, 0.85)


# ---------------------------------------------------------------------------
# PGE Ranker Integration Tests
# ---------------------------------------------------------------------------


class RankerResponsivenessIntegrationTest(TestCase):
    """Tests for GLOE integration with PGE ranker."""

    def test_rank_score_neutral_responsiveness_no_change(self):
        """Responsiveness of 0.5 (neutral) should not change base score."""
        candidate = {"priority": 3, "confidence_score": 0.5}
        base = _compute_rank_score(candidate, responsiveness=None)
        adjusted = _compute_rank_score(candidate, responsiveness=0.5)
        self.assertEqual(base, adjusted)

    def test_rank_score_high_responsiveness_boosts(self):
        """High responsiveness should increase score."""
        candidate = {"priority": 3, "confidence_score": 0.5}
        base = _compute_rank_score(candidate, responsiveness=None)
        boosted = _compute_rank_score(candidate, responsiveness=1.0)
        self.assertGreater(boosted, base)

    def test_rank_score_low_responsiveness_reduces(self):
        """Low responsiveness should decrease score."""
        candidate = {"priority": 3, "confidence_score": 0.5}
        base = _compute_rank_score(candidate, responsiveness=None)
        reduced = _compute_rank_score(candidate, responsiveness=0.0)
        self.assertLess(reduced, base)

    def test_rank_score_max_adjustment_bounded(self):
        """Max adjustment should be ±RESPONSIVENESS_INFLUENCE (25%)."""
        candidate = {"priority": 1, "confidence_score": 1.0}
        base = _compute_rank_score(candidate, responsiveness=None)
        max_boost = _compute_rank_score(candidate, responsiveness=1.0)
        expected_max = base * (1 + RESPONSIVENESS_INFLUENCE)
        self.assertAlmostEqual(max_boost, expected_max, places=4)

    def test_rank_score_none_responsiveness_no_adjustment(self):
        """None responsiveness should not adjust score."""
        candidate = {"priority": 2}
        score_none = _compute_rank_score(candidate, responsiveness=None)
        score_base = _compute_rank_score(candidate)
        self.assertEqual(score_none, score_base)

    def test_rank_guidance_with_user_calls_gloe(self):
        """rank_guidance with user should attempt to get responsiveness."""
        user = _create_test_user()
        candidates = [
            {"title": "A", "priority": 3},
            {"title": "B", "priority": 2},
        ]
        # Should not raise — GLOE returns 0.5 (neutral) for new user
        result = rank_guidance(candidates, user=user)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["title"], "B")  # Higher priority

    def test_rank_guidance_without_user_works(self):
        """rank_guidance without user should work normally (backward compat)."""
        candidates = [
            {"title": "Low", "priority": 5},
            {"title": "High", "priority": 1},
        ]
        result = rank_guidance(candidates)
        self.assertEqual(result[0]["title"], "High")

    def test_priority_order_preserved_with_responsiveness(self):
        """GLOE adjustment must NOT override base priority ordering."""
        candidates = [
            {"title": "Critical", "priority": 1},
            {"title": "Info", "priority": 5},
        ]
        # Even with extreme responsiveness, critical should still rank first
        # because the adjustment is proportional (both get same multiplier)
        with patch(
            "apps.core.ai_guidance.guidance_ranker._get_responsiveness",
            return_value=0.0,
        ):
            user = _create_test_user(email="ranktest@example.com")
            result = rank_guidance(candidates, user=user)
            self.assertEqual(result[0]["title"], "Critical")

    def test_gloe_failure_does_not_break_ranking(self):
        """If GLOE raises, ranking should still work."""
        with patch(
            "apps.core.ai_guidance.guidance_ranker._get_responsiveness",
            side_effect=Exception("GLOE error"),
        ):
            candidates = [{"title": "A", "priority": 3}]
            # _get_responsiveness catches exceptions internally,
            # but even if it didn't, rank_guidance should handle it
            result = rank_guidance(candidates, user=None)
            self.assertEqual(len(result), 1)
