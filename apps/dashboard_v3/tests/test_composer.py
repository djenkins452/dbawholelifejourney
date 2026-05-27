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
        self.assertIn(summary["trajectory"], ("improving", "mixed"))

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
        self.assertEqual(_derive_trajectory([{}], [], None), "improving")
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
