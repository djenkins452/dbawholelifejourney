"""
Tests for the SAE journey state block and the CoS journey context block.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.faith.journey.context import build_journey_context_block
from apps.faith.journey.models import JourneyArc, JourneyPath, UserJourney
from apps.faith.journey.state import build_journey_state, compute_momentum_score


User = get_user_model()


def _u(email="state@example.com"):
    return User.objects.create_user(email=email, password="x" * 20)


class JourneyStateTests(TestCase):
    def test_empty_block_when_no_active_journey(self):
        user = _u()
        state = build_journey_state(user)
        self.assertFalse(state["active"])
        self.assertEqual(state["current_arc_day"], None)
        self.assertEqual(state["momentum_score"], 1.0)
        self.assertEqual(state["application_committed_this_week"], 0)

    def test_populated_block_for_active_journey(self):
        user = _u()
        path = JourneyPath.objects.create(slug="p", name="P", narrative_overview="x", difficulty_default="standard")
        arc = JourneyArc.objects.create(
            journey_path=path, slug="a", name="Arc A", era_label="Era",
            order=1, opening_note="x", closing_note="x", estimated_days=21,
        )
        UserJourney.objects.create(
            user=user, journey_path=path, current_arc=arc,
            current_day_number=6, preferred_difficulty="deeper",
        )
        state = build_journey_state(user)
        self.assertTrue(state["active"])
        self.assertEqual(state["journey_path_slug"], "p")
        self.assertEqual(state["current_arc_slug"], "a")
        self.assertEqual(state["current_arc_day"], 6)
        self.assertEqual(state["current_arc_total_days"], 21)
        self.assertEqual(state["preferred_difficulty"], "deeper")
        self.assertIsNone(state["days_since_last_read"])  # never engaged
        self.assertEqual(state["momentum_score"], 1.0)

    def test_days_since_last_read_uses_last_engaged_at_not_visited(self):
        """Welcome-back tracking (last_visited_at) must not mask reading gaps."""
        user = _u()
        path = JourneyPath.objects.create(slug="p", name="P", narrative_overview="x", difficulty_default="standard")
        arc = JourneyArc.objects.create(
            journey_path=path, slug="a", name="A", order=1,
            opening_note="x", closing_note="x", estimated_days=10,
        )
        now = timezone.now()
        UserJourney.objects.create(
            user=user, journey_path=path, current_arc=arc,
            current_day_number=1,
            last_engaged_at=now - timedelta(days=10),
            last_visited_at=now,  # user just opened the page — should NOT zero out days_since_read
        )
        state = build_journey_state(user)
        self.assertEqual(state["days_since_last_read"], 10)


class MomentumScoreTests(TestCase):
    def test_no_data_returns_default(self):
        self.assertEqual(compute_momentum_score(None), 1.0)

    def test_under_three_days_is_full(self):
        self.assertEqual(compute_momentum_score(0), 1.0)
        self.assertEqual(compute_momentum_score(2), 1.0)

    def test_decays_linearly_between_3_and_21(self):
        self.assertEqual(compute_momentum_score(3), 1.0)
        # day 12 = midpoint between 3 and 21 → score ≈ 0.5
        self.assertAlmostEqual(compute_momentum_score(12), 0.5, places=2)
        self.assertEqual(compute_momentum_score(21), 0.0)

    def test_caps_at_zero_beyond_21(self):
        self.assertEqual(compute_momentum_score(100), 0.0)


class JourneyContextBlockTests(TestCase):
    def test_inactive_when_no_journey(self):
        user = _u()
        block = build_journey_context_block(user)
        self.assertEqual(block, {"active": False})

    def test_active_block_omits_momentum_score(self):
        """momentum_score is internal-only — must NOT appear in Beth's context."""
        user = _u()
        path = JourneyPath.objects.create(slug="p", name="P", narrative_overview="x", difficulty_default="standard")
        arc = JourneyArc.objects.create(
            journey_path=path, slug="a", name="A", order=1,
            opening_note="x", closing_note="x", estimated_days=10,
        )
        UserJourney.objects.create(
            user=user, journey_path=path, current_arc=arc, current_day_number=4,
        )
        block = build_journey_context_block(user)
        self.assertTrue(block["active"])
        self.assertEqual(block["journey_name"], "P")
        self.assertEqual(block["arc_day"], 4)
        # Internal-only fields MUST be omitted from Beth-facing context.
        self.assertNotIn("momentum_score", block)
        self.assertNotIn("application_committed_this_week", block)
