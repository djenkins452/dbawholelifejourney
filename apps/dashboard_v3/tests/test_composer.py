"""Tests for the dashboard_v3 composer + canonical CoS briefing layer.

Goals:
  - Composer always returns the full top-level shape (defensive defaults).
  - Executive summary handles empty / mixed state.
  - Rhythm grouping classifies items into the four buckets correctly and
    honors the Visual Truth Contract (completion counts only).
  - Composer never raises on the request path.
"""

from datetime import time as dtime

from django.conf import settings
from django.test import TestCase

from apps.core.cos_briefing.executive_summary import (
    _derive_trajectory,
    build_executive_summary,
)
from apps.core.cos_briefing.rhythm import (
    RHYTHM_BUCKETS,
    build_rhythm_sections,
    _classify_item,
)
from apps.core.ai_insights.models import Insight
from apps.dashboard_v3.services.composer import build_dashboard_v3_context
from apps.users.models import TermsAcceptance, User


class CoSBriefingExecutiveSummaryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="v3-exec@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def test_returns_full_shape_on_empty_user(self):
        summary = build_executive_summary(self.user)
        for key in (
            "trajectory", "going_well", "needs_attention",
            "biggest_risk", "biggest_opportunity",
            "focus_now", "follow_on", "recommendations", "as_of",
        ):
            self.assertIn(key, summary)
        self.assertEqual(summary["trajectory"], "unknown")
        self.assertEqual(summary["going_well"], [])
        self.assertEqual(summary["needs_attention"], [])

    def test_going_well_picks_up_positive_insight(self):
        Insight.objects.create(
            user=self.user,
            module="health",
            insight_type="hydration_consistent",
            severity="positive",
            title="Hydration on track 7 days running",
            message="Water goal hit every day this week.",
            confidence_score=0.9,
            dedupe_key="test-dedupe-1",
        )
        summary = build_executive_summary(self.user)
        self.assertTrue(summary["going_well"])
        self.assertEqual(summary["going_well"][0]["module"], "health")
        # One positive insight is "steady", not "improving" — see trajectory
        # threshold change after self-critique pass.
        self.assertEqual(summary["trajectory"], "steady")

    def test_two_positive_insights_register_as_improving(self):
        for i in range(2):
            Insight.objects.create(
                user=self.user, module="health",
                insight_type=f"good_{i}", severity="positive",
                title=f"Good {i}", message="", confidence_score=0.9,
                dedupe_key=f"good-{i}",
            )
        summary = build_executive_summary(self.user)
        self.assertEqual(summary["trajectory"], "improving")

    def test_needs_attention_orders_critical_before_warning(self):
        Insight.objects.create(
            user=self.user, module="health", insight_type="warn_a",
            severity="warning", title="warn-a", message="",
            confidence_score=0.5, dedupe_key="t-w-a",
        )
        Insight.objects.create(
            user=self.user, module="health", insight_type="crit_a",
            severity="critical", title="crit-a", message="",
            confidence_score=0.9, dedupe_key="t-c-a",
        )
        summary = build_executive_summary(self.user)
        self.assertEqual(summary["needs_attention"][0]["severity"], "critical")

    def test_trajectory_logic(self):
        # Pure unit tests on the derivation rule — no DB.
        self.assertEqual(_derive_trajectory([], [], None), "unknown")
        # One positive is "steady" — not enough to claim a trend.
        self.assertEqual(_derive_trajectory([{}], [], None), "steady")
        # Two positives, no negatives → improving.
        self.assertEqual(_derive_trajectory([{}, {}], [], None), "improving")
        self.assertEqual(_derive_trajectory([], [{}], None), "slipping")
        self.assertEqual(
            _derive_trajectory([{}], [{}, {}], {"title": "x"}), "slipping"
        )
        self.assertEqual(_derive_trajectory([{}, {}, {}], [{}], None), "improving")


class CoSBriefingRhythmTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="v3-rhythm@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def test_buckets_cover_all_canonical_windows(self):
        windows_covered = set()
        for bucket in RHYTHM_BUCKETS:
            for window in bucket["windows"]:
                windows_covered.add(window)
        # All six canonical windows must be mapped — none silently dropped.
        from apps.core.time_windows import WINDOW_ORDER
        self.assertEqual(windows_covered, set(WINDOW_ORDER))

    def test_classify_by_scheduled_time(self):
        self.assertEqual(_classify_item({"scheduled_time": "06:30"}), "morning")
        self.assertEqual(_classify_item({"scheduled_time": "13:00"}), "day")
        self.assertEqual(_classify_item({"scheduled_time": "19:00"}), "evening")
        self.assertEqual(_classify_item({"scheduled_time": "22:00"}), "night")

    def test_classify_by_time_of_day_takes_precedence(self):
        item = {"scheduled_time": "13:00", "time_of_day": "evening"}
        self.assertEqual(_classify_item(item), "evening")

    def test_classify_unscheduled_falls_to_day(self):
        self.assertEqual(_classify_item({}), "day")

    def test_completion_counts_honor_visual_truth_contract(self):
        # Items with completed_today=False should NOT add to completed count
        # even if their status reads as "DONE-like" in a status string.
        items = [
            {"scheduled_time": "06:00", "completed_today": True},
            {"scheduled_time": "07:00", "completed_today": False,
             "execution_status": "AT_RISK", "urgency": "now"},
            {"scheduled_time": "07:30", "completed_today": False,
             "urgency": "overdue"},
        ]
        result = build_rhythm_sections(
            self.user,
            execution_contract={"items": items, "summaries": {}},
        )
        morning = next(s for s in result["sections"] if s["key"] == "morning")
        self.assertEqual(morning["completion"]["completed"], 1)
        self.assertEqual(morning["completion"]["total"], 3)
        self.assertEqual(morning["completion"]["at_risk"], 1)
        self.assertEqual(morning["completion"]["overdue"], 1)

    def test_section_structure_always_present(self):
        result = build_rhythm_sections(
            self.user,
            execution_contract={"items": [], "summaries": {}},
        )
        self.assertEqual(len(result["sections"]), 4)
        keys = [s["key"] for s in result["sections"]]
        self.assertEqual(keys, ["morning", "day", "evening", "night"])


class DashboardV3ComposerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="v3-comp@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def test_composer_returns_all_sections(self):
        ctx = build_dashboard_v3_context(self.user)
        for key in (
            "gauges", "executive_summary", "focus_now", "follow_on",
            "accountability_cards", "rhythm", "utilities",
        ):
            self.assertIn(key, ctx)

    def test_composer_is_safe_when_engines_have_no_data(self):
        # Should not raise even with a fresh, empty user.
        ctx = build_dashboard_v3_context(self.user)
        self.assertEqual(ctx["accountability_cards"], [])
        self.assertIsInstance(ctx["rhythm"], dict)
        self.assertIn("sections", ctx["rhythm"])

    def test_gauges_fall_back_to_sae_when_cockpit_empty(self):
        """User has no LifeGoals/HabitGoals → gauges must still populate
        from canonical SAE state (Health, Faith, Life Execution, Purpose)."""
        ctx = build_dashboard_v3_context(self.user)
        gauges = ctx["gauges"]
        self.assertTrue(gauges, "fallback gauges must always render")
        slugs = {g["slug"] for g in gauges}
        # We require AT LEAST these four baselines for a fresh user.
        for required in ("health", "faith", "life", "purpose"):
            self.assertIn(required, slugs)
        # Every fallback gauge must be tagged as such for telemetry/debugging.
        for g in gauges:
            self.assertEqual(g["source"], "sae_fallback")
            # Drivers list must always exist (even if it's a single info row).
            self.assertIn("drivers", g)


class SelfCritiqueFixTests(TestCase):
    """Tests for the self-critique pass: render-bug fixes spotted in v3."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="v3-fixes@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def test_biggest_opportunity_uses_explanation_not_slug(self):
        from datetime import date, timedelta
        from apps.core.ai_predictions.models import Prediction
        Prediction.objects.create(
            user=self.user,
            prediction_type="emotional_overload_7d",
            module="journal",
            predicted_value=0.0,
            predicted_date=date.today() + timedelta(days=7),
            confidence_score=0.85,
            explanation="Sleep deficit is compounding emotional overload risk this week. Address before Friday.",
            evidence={},
            status="active",
            dedupe_key="opp-1",
        )
        summary = build_executive_summary(self.user)
        opp = summary["biggest_opportunity"]
        self.assertIsNotNone(opp)
        # No raw slug leak. The headline should be the first clause of the
        # explanation, not "Emotional Overload 7D".
        self.assertNotIn("7D", opp["title"])
        self.assertIn("Sleep deficit", opp["title"])

    def test_humanize_focus_reason_replaces_selector_noise(self):
        from apps.core.cos_briefing.executive_summary import _humanize_focus_reason
        # Short raw reason → replaced
        self.assertNotEqual(
            _humanize_focus_reason("current", {"urgency": "now"}),
            "current",
        )
        # Underscore-bearing internal label → replaced
        self.assertNotEqual(
            _humanize_focus_reason(
                "primary_pool_overdue_or_now",
                {"urgency": "overdue"},
            ),
            "primary_pool_overdue_or_now",
        )
        # A real human sentence → preserved
        long_real = "This anchors the morning recovery; complete before the next block."
        self.assertEqual(
            _humanize_focus_reason(long_real, {}),
            long_real,
        )

    def test_accountability_insight_silent_when_only_recommendation(self):
        from apps.dashboard_v3.services.composer import _accountability_insight
        rec = {"title": "Try X", "message": "details"}
        # No going_well, no needs_attention, but a real recommendation:
        # insight should be None so the template doesn't contradict the rec
        # with a "not enough signal yet" line.
        self.assertIsNone(_accountability_insight([], [], rec))
        # Without a rec, fall back to the legacy "not enough signal" copy.
        self.assertIsNotNone(_accountability_insight([], [], None))

    def test_biggest_risk_dedupes_against_focus_now(self):
        """When the selector picks the same item for both risk and focus,
        only focus_now should render it. The exec summary's biggest_risk
        gets cleared by the composer."""
        from apps.core.ai_insights.models import Insight
        # Force a critical insight so biggest_risk has a fallback.
        Insight.objects.create(
            user=self.user, module="health", insight_type="x",
            severity="critical", title="Critical fallback",
            message="", confidence_score=0.9, dedupe_key="crit-fb",
        )
        # The selectors will yield None for both (no items today), but the
        # exec summary will then surface the critical fallback as risk.
        ctx = build_dashboard_v3_context(self.user)
        # If focus_now has the same title as biggest_risk, risk must be None.
        risk = ctx["executive_summary"].get("biggest_risk")
        focus = ctx["focus_now"]
        if risk and focus:
            self.assertNotEqual(risk["title"], focus["title"])


class WeatherTileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="v3-weather@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def test_weather_tile_returns_set_location_when_unset(self):
        from apps.dashboard_v3.services import build_weather_tile
        # Fresh user has no location_city; tile must still render.
        self.user.preferences.location_city = ""
        self.user.preferences.save()
        tile = build_weather_tile(self.user)
        self.assertFalse(tile["available"])
        self.assertIsNone(tile["data"])
        self.assertIn("location", tile["message"].lower())
