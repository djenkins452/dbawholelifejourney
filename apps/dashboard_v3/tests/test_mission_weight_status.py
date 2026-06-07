"""Mission Card Weight Visibility — always-on Weight Status block.

Trust contract under test:
  · The block renders for every weight-driven mission in every state
    (improving, stalled, trending up, no weigh-in, sync stale, at-target).
  · Only the "ok" tone — current ≤ target by canonical data — may use
    completion-resembling visuals (✓ glyph). Every other state uses
    tonal accents only (Visual Truth Contract).
  · Zero new DB queries: helper consumes the already-loaded `next_milestone`
    and the SAE health state already read by `_read_mission_states`.
  · Non-weight missions: the block is None (omitted in template).
"""

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.dashboard_v3.services.composer import _build_mission_weight_status
from apps.purpose.models import GoalMilestone, LifeGoal
from apps.users.models import TermsAcceptance


User = get_user_model()


def _make_user(email="mwv@test.com"):
    u = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=u,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _goal_with_weight_milestone(user, *, target="289.9", title="Goal Weight of 289.9"):
    goal = LifeGoal.objects.create(
        user=user, title="France 2027 Family 10K Mission",
        description="test", status="active", is_primary_mission=True,
    )
    milestone = GoalMilestone.objects.create(
        goal=goal, title=title,
        objective_metric="weight_lb",
        objective_target_value=Decimal(target),
        objective_operator="lte",
        completed=False,
    )
    return goal, milestone


# ── Truth: state matrix coverage ──────────────────────────────────


class TrendingDownTests(TestCase):
    """Weight is above target but trending toward goal — encouraged tone,
    NO ✓ glyph (not yet at target by canonical data)."""

    def setUp(self):
        self.user = _make_user("td@test.com")
        self.goal, self.milestone = _goal_with_weight_milestone(self.user)

    def test_above_target_decreasing_tone_down(self):
        health = {
            "weight_current": 296.4, "weight_unit": "lb",
            "weight_trend": "decreasing", "weight_change_30d": -1.8,
            "weight_sync_stale": False,
        }
        ws = _build_mission_weight_status(self.goal, health, self.milestone)
        self.assertIsNotNone(ws)
        self.assertTrue(ws["has_data"])
        self.assertEqual(ws["current"], 296.4)
        self.assertEqual(ws["target"], 289.9)
        self.assertAlmostEqual(ws["to_next"], 6.5, places=1)
        self.assertEqual(ws["tone"], "down")
        self.assertIn("6.5", ws["headline"])
        self.assertIn("next milestone", ws["headline"])
        self.assertEqual(ws["subline"], "Target: 289.9 lb")
        # 30d change is a real negative — sign + display present
        self.assertEqual(ws["change_sign"], "down")
        self.assertIn("-1.8", ws["change_display"])


class StalledTests(TestCase):
    """Weight stable, above target. Truthful neutral — no false hope, no
    false alarm."""

    def setUp(self):
        self.user = _make_user("st@test.com")
        self.goal, self.milestone = _goal_with_weight_milestone(self.user, target="284.9")

    def test_above_target_stable_tone_flat(self):
        health = {
            "weight_current": 289.0, "weight_unit": "lb",
            "weight_trend": "stable", "weight_change_30d": 0.0,
            "weight_sync_stale": False,
        }
        ws = _build_mission_weight_status(self.goal, health, self.milestone)
        self.assertEqual(ws["tone"], "flat")
        self.assertEqual(ws["trend_label"], "Stable")
        # 30d delta of 0 must still render the row (0.0 lb (30d)) — truth.
        self.assertEqual(ws["change_sign"], "flat")
        self.assertIn("0.0", ws["change_display"])


class TrendingUpTests(TestCase):
    """Weight is above target AND climbing. Truth-first red tone. No
    softening, no hiding."""

    def setUp(self):
        self.user = _make_user("tu@test.com")
        self.goal, self.milestone = _goal_with_weight_milestone(self.user, target="284.9")

    def test_above_target_increasing_tone_up(self):
        health = {
            "weight_current": 296.2, "weight_unit": "lb",
            "weight_trend": "increasing", "weight_change_30d": 3.4,
            "weight_sync_stale": False,
        }
        ws = _build_mission_weight_status(self.goal, health, self.milestone)
        self.assertEqual(ws["tone"], "up")
        self.assertEqual(ws["change_sign"], "up")
        self.assertIn("+3.4", ws["change_display"])
        self.assertNotIn("✓", ws["headline"])
        self.assertNotIn("✓", ws["subline"])


class AtTargetTests(TestCase):
    """The ONLY completion-resembling state — Visual Truth Contract."""

    def setUp(self):
        self.user = _make_user("at@test.com")
        self.goal, self.milestone = _goal_with_weight_milestone(self.user, target="289.9")

    def test_at_target_exact_boundary_tone_ok(self):
        health = {
            "weight_current": 289.9, "weight_unit": "lb",
            "weight_trend": "stable", "weight_change_30d": -0.5,
            "weight_sync_stale": False,
        }
        ws = _build_mission_weight_status(self.goal, health, self.milestone)
        self.assertEqual(ws["tone"], "ok")
        self.assertEqual(ws["headline"], "At milestone target")
        self.assertIn("✓", ws["subline"])

    def test_below_target_tone_ok(self):
        health = {
            "weight_current": 284.7, "weight_unit": "lb",
            "weight_trend": "decreasing", "weight_change_30d": -2.1,
            "weight_sync_stale": False,
        }
        ws = _build_mission_weight_status(self.goal, health, self.milestone)
        self.assertEqual(ws["tone"], "ok")
        self.assertLess(ws["to_next"], 0)


class NoWeighInTests(TestCase):
    """No current weight available — must still render with the target
    only. No fabricated trend."""

    def setUp(self):
        self.user = _make_user("nw@test.com")
        self.goal, self.milestone = _goal_with_weight_milestone(self.user, target="284.9")

    def test_no_current_weight_renders_target_only(self):
        health = {
            "weight_current": None, "weight_unit": "lb",
            "weight_trend": "insufficient_data", "weight_change_30d": None,
            "weight_sync_stale": False,
        }
        ws = _build_mission_weight_status(self.goal, health, self.milestone)
        self.assertIsNotNone(ws)
        self.assertFalse(ws["has_data"])
        self.assertIsNone(ws["current"])
        self.assertEqual(ws["target"], 284.9)
        self.assertEqual(ws["tone"], "flat")
        self.assertEqual(ws["headline"], "No recent weigh-in")
        self.assertIn("284.9", ws["subline"])
        self.assertIsNone(ws["change_display"])

    def test_empty_health_state_renders_with_target_no_crash(self):
        """Defensive: even an entirely empty SAE health dict must render."""
        ws = _build_mission_weight_status(self.goal, {}, self.milestone)
        self.assertIsNotNone(ws)
        self.assertFalse(ws["has_data"])
        self.assertEqual(ws["target"], 284.9)


class SyncStaleTests(TestCase):
    """Sync stale overlays the truth — it does NOT replace it."""

    def setUp(self):
        self.user = _make_user("ss@test.com")
        self.goal, self.milestone = _goal_with_weight_milestone(self.user, target="289.9")

    def test_sync_stale_overlays_with_data(self):
        health = {
            "weight_current": 296.4, "weight_unit": "lb",
            "weight_trend": "decreasing", "weight_change_30d": -1.8,
            "weight_sync_stale": True,
        }
        ws = _build_mission_weight_status(self.goal, health, self.milestone)
        self.assertTrue(ws["sync_stale"])
        # Real data still rendered — sync stale never hides truth.
        self.assertTrue(ws["has_data"])
        self.assertEqual(ws["current"], 296.4)
        self.assertEqual(ws["tone"], "down")

    def test_sync_stale_overlays_with_no_data(self):
        health = {
            "weight_current": None, "weight_sync_stale": True,
            "weight_trend": "insufficient_data",
        }
        ws = _build_mission_weight_status(self.goal, health, self.milestone)
        self.assertTrue(ws["sync_stale"])
        self.assertFalse(ws["has_data"])


# ── Non-weight missions: block omitted ────────────────────────────


class NonWeightMissionTests(TestCase):
    """Non-weight missions must NOT force this block to render."""

    def setUp(self):
        self.user = _make_user("nw-miss@test.com")
        self.goal = LifeGoal.objects.create(
            user=self.user, title="Read 50 books", description="",
            status="active", is_primary_mission=True,
        )
        # Achievement milestone — no objective_metric
        self.milestone = GoalMilestone.objects.create(
            goal=self.goal, title="Book 1", completed=False,
        )

    def test_no_weight_milestone_returns_none(self):
        health = {"weight_current": 200.0, "weight_unit": "lb"}
        ws = _build_mission_weight_status(self.goal, health, self.milestone)
        self.assertIsNone(ws)

    def test_no_milestone_at_all_returns_none(self):
        # Edge case: no next milestone, no milestones at all.
        goal2 = LifeGoal.objects.create(
            user=self.user, title="Side mission", description="",
            status="active", is_primary_mission=False,
        )
        ws = _build_mission_weight_status(goal2, {}, None)
        self.assertIsNone(ws)


# ── Fallback target source: any objective-weight milestone on goal ──


class TargetSourceFallbackTests(TestCase):
    """When next_milestone isn't itself a weight milestone, fall back to
    the smallest objective_target_value on the goal so the block still
    renders for a fully-completed weight mission."""

    def setUp(self):
        self.user = _make_user("ts@test.com")
        self.goal = LifeGoal.objects.create(
            user=self.user, title="Mixed mission", description="",
            status="active", is_primary_mission=True,
        )
        # Completed weight milestone
        GoalMilestone.objects.create(
            goal=self.goal, title="Goal Weight of 289.9",
            objective_metric="weight_lb",
            objective_target_value=Decimal("289.9"),
            objective_operator="lte",
            completed=True,
        )
        # Next-in-chain is an achievement (no objective_metric)
        self.next_ach = GoalMilestone.objects.create(
            goal=self.goal, title="Run 5K", completed=False,
        )

    def test_falls_back_to_weight_milestone_when_next_is_achievement(self):
        health = {
            "weight_current": 285.0, "weight_unit": "lb",
            "weight_trend": "decreasing", "weight_change_30d": -2.0,
            "weight_sync_stale": False,
        }
        ws = _build_mission_weight_status(self.goal, health, self.next_ach)
        self.assertIsNotNone(ws)
        self.assertEqual(ws["target"], 289.9)
        # 285.0 ≤ 289.9 → ok
        self.assertEqual(ws["tone"], "ok")


# ── Truth: tone follows TREND, not distance ──────────────────────


class ToneFollowsTrendTests(TestCase):
    """Even close to target, an upward trend gets the truthful "up" tone.
    Even far from target, a downward trend gets the encouraging "down"
    tone. This locks the contract: tone reflects DIRECTION OF TRAVEL."""

    def setUp(self):
        self.user = _make_user("tone@test.com")
        self.goal, self.milestone = _goal_with_weight_milestone(self.user, target="289.9")

    def test_close_to_target_but_increasing_is_up(self):
        health = {
            "weight_current": 290.1, "weight_unit": "lb",  # 0.2 lb above
            "weight_trend": "increasing", "weight_change_30d": 1.2,
            "weight_sync_stale": False,
        }
        ws = _build_mission_weight_status(self.goal, health, self.milestone)
        self.assertEqual(ws["tone"], "up")

    def test_far_from_target_but_decreasing_is_down(self):
        health = {
            "weight_current": 320.0, "weight_unit": "lb",  # 30+ lb above
            "weight_trend": "decreasing", "weight_change_30d": -4.0,
            "weight_sync_stale": False,
        }
        ws = _build_mission_weight_status(self.goal, health, self.milestone)
        self.assertEqual(ws["tone"], "down")


# ── Visual Truth Contract enforcement ────────────────────────────


class VisualTruthContractTests(TestCase):
    """The ✓ glyph appears in `subline` ONLY in the `ok` tone branch."""

    def setUp(self):
        self.user = _make_user("vtc@test.com")
        self.goal, self.milestone = _goal_with_weight_milestone(self.user, target="289.9")

    def test_check_glyph_only_in_ok_subline(self):
        for trend, current in [
            ("decreasing", 295.0),
            ("stable", 295.0),
            ("increasing", 295.0),
            ("insufficient_data", 295.0),
        ]:
            health = {
                "weight_current": current, "weight_unit": "lb",
                "weight_trend": trend, "weight_change_30d": 0.0,
                "weight_sync_stale": False,
            }
            ws = _build_mission_weight_status(self.goal, health, self.milestone)
            self.assertNotEqual(ws["tone"], "ok", f"trend={trend} should never be 'ok'")
            self.assertNotIn("✓", ws["headline"])
            self.assertNotIn("✓", ws["subline"])

    def test_check_glyph_present_in_ok_subline(self):
        health = {
            "weight_current": 289.0, "weight_unit": "lb",
            "weight_trend": "decreasing", "weight_change_30d": -1.0,
            "weight_sync_stale": False,
        }
        ws = _build_mission_weight_status(self.goal, health, self.milestone)
        self.assertEqual(ws["tone"], "ok")
        self.assertIn("✓", ws["subline"])


# ── Zero-query contract ──────────────────────────────────────────


class ZeroQueryContractTests(TestCase):
    """The helper must add ZERO database queries on the request path.
    `next_milestone` is already evaluated by `_build_mission_card`, and
    `health_state` is already read by `_read_mission_states`. The only
    DB touch is the fallback scan over `goal.milestones.all()` which is
    bounded to the goal's own milestones — and which the composer already
    iterates upstream for the progress ring.
    """

    def setUp(self):
        self.user = _make_user("zq@test.com")
        self.goal, self.milestone = _goal_with_weight_milestone(self.user, target="289.9")

    def test_helper_under_two_queries(self):
        health = {
            "weight_current": 290.0, "weight_unit": "lb",
            "weight_trend": "decreasing", "weight_change_30d": -1.0,
            "weight_sync_stale": False,
        }
        # Warm Decimal access — Python-level only.
        _ = self.milestone.objective_target_value

        with self.assertNumQueries(0):
            # next_milestone is passed in (already loaded); helper does
            # not need to scan milestones in the happy path.
            _build_mission_weight_status(self.goal, health, self.milestone)

    def test_fallback_scan_is_bounded(self):
        """Fallback path (next_milestone NOT a weight milestone) does
        ONE bounded scan over the goal's own milestones, which the
        composer already iterates for the progress ring. ≤2 queries
        keeps the per-card overhead invisible."""
        # Achievement next_milestone forces the fallback scan.
        ach = GoalMilestone.objects.create(
            goal=self.goal, title="Run 5K", completed=False,
        )
        health = {
            "weight_current": 290.0, "weight_unit": "lb",
            "weight_trend": "stable", "weight_change_30d": 0.0,
            "weight_sync_stale": False,
        }
        with self.assertNumQueries(1):
            _build_mission_weight_status(self.goal, health, ach)
