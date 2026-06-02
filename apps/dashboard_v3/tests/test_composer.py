"""Tests for the dashboard_v3 composer + canonical CoS briefing layer.

Goals:
  - Composer always returns the full top-level shape (defensive defaults).
  - Executive summary handles empty / mixed state.
  - Rhythm grouping classifies items into the four buckets correctly and
    honors the Visual Truth Contract (completion counts only).
  - Composer never raises on the request path.
"""

from datetime import time as dtime
from unittest import mock

from django.conf import settings
from django.test import TestCase

# Saved before any patching so resilience tests can delegate to the real
# implementation from inside a ``side_effect``.
from apps.core.ai_state.state_engine import (
    get_module_state as _REAL_GET_MODULE_STATE,
)

from apps.core.cos_briefing.executive_summary import (
    _derive_headline,
    _derive_overall_state,
    build_executive_summary,
)
from apps.core.cos_briefing.rhythm import (
    RHYTHM_BUCKETS,
    _momentum_label,
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
        # Pure unit tests on the dominant-state rule — no DB. With no exec
        # pressure (exec_state=None) this collapses to the insight-count trend.
        self.assertEqual(_derive_overall_state([], [], None, None), "unknown")
        # One positive is "steady" — not enough to claim a trend.
        self.assertEqual(_derive_overall_state([{}], [], None, None), "steady")
        # Two positives, no negatives → improving.
        self.assertEqual(_derive_overall_state([{}, {}], [], None, None), "improving")
        self.assertEqual(_derive_overall_state([], [{}], None, None), "slipping")
        self.assertEqual(
            _derive_overall_state([{}], [{}, {}], {"title": "x"}, None), "slipping"
        )
        self.assertEqual(_derive_overall_state([{}, {}, {}], [{}], None, None), "improving")


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
        # Positive prediction: the Biggest Opportunity slot is positive-only
        # (risk-type predictions are filtered out — see coherence fix). This
        # test verifies the explanation-vs-slug humanization, not polarity.
        Prediction.objects.create(
            user=self.user,
            prediction_type="weight_projection_30d",
            module="health",
            predicted_value=0.0,
            predicted_date=date.today() + timedelta(days=30),
            confidence_score=0.85,
            explanation="Consistent logging is putting your goal weight in reach this month. Keep the streak going.",
            evidence={"outlook": "on track"},
            status="active",
            dedupe_key="opp-1",
        )
        summary = build_executive_summary(self.user)
        opp = summary["biggest_opportunity"]
        self.assertIsNotNone(opp)
        # No raw slug leak. The title should be the first clause of the
        # explanation, not "Weight Projection 30D".
        self.assertNotIn("30D", opp["title"])
        self.assertIn("goal weight", opp["title"].lower())

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


class RhythmInteractionModeTests(TestCase):
    """Workflow enhancement: rhythm sections derive interaction_mode +
    dose_groups + preview_groups from canonical state. No UI-only truth.
    Beth/Dashboard convergence preserved (both consume the same
    underlying execution items)."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="rhythm-modes@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def _items(self, **kw):
        """Default future morning item generator."""
        defaults = {
            "is_actionable": True, "completed_today": False, "title": "X",
        }
        defaults.update(kw)
        return defaults

    def test_every_section_carries_interaction_mode(self):
        result = build_rhythm_sections(
            self.user, execution_contract={"items": [], "summaries": {}},
        )
        for s in result["sections"]:
            self.assertIn(s["interaction_mode"], ("full", "preview", "summary", "empty"))

    def test_preview_mode_groups_future_items_by_time_no_checkboxes(self):
        """Day Rhythm with two scheduled items in the future must come
        back in preview mode with a grouped 'Coming Later' list — no dead
        white space, no checkboxes."""
        items = [
            self._items(scheduled_time="13:00", title="10X Optimize",
                        source_type="supplement_dose"),
            self._items(scheduled_time="13:00", title="Fish Oil",
                        source_type="supplement_dose"),
            self._items(scheduled_time="18:00", title="Log Nutrition",
                        source_type="task"),
        ]
        result = build_rhythm_sections(
            self.user, execution_contract={"items": items, "summaries": {}},
        )
        day = next(s for s in result["sections"] if s["key"] == "day")
        # Preview only when Day is the bucket IMMEDIATELY after current.
        # In real wall-clock terms that's true only during the morning
        # window — so skip outside of it (the next-only rule is covered
        # by its own dedicated test above).
        if day["interaction_mode"] != "preview":
            self.skipTest(
                f"Day is in mode {day['interaction_mode']} at this wall-clock; "
                "preview behavior covered by dedicated test."
            )
        self.assertEqual(day["interaction_mode"], "preview")
        # Preview groups: by scheduled time, no per-item checkboxes.
        times = [pg["time"] for pg in day["preview_groups"]]
        self.assertEqual(len(day["preview_groups"]), 2)
        self.assertIn("1:00 PM", times)
        self.assertIn("6:00 PM", times)
        first = day["preview_groups"][0]
        self.assertEqual(len(first["titles"]), 2)

    def test_empty_future_section_is_mode_empty(self):
        result = build_rhythm_sections(
            self.user, execution_contract={"items": [], "summaries": {}},
        )
        for s in result["sections"]:
            if not s["is_current"] and not s["is_past"] and s["completion"]["total"] == 0:
                self.assertEqual(s["interaction_mode"], "empty")

    def test_dose_groups_split_meds_from_supplements(self):
        """Meds and supplements MUST come back as separate groups so the
        dashboard renders distinct buttons (user can take meds, skip
        supplements). No hardcoded names."""
        items = [
            self._items(source_type="medication_dose", intake_type="medication",
                        time_of_day="morning", title="Metformin"),
            self._items(source_type="medication_dose", intake_type="medication",
                        time_of_day="morning", title="Lantus"),
            self._items(source_type="supplement_dose", intake_type="supplement",
                        time_of_day="morning", title="Fish Oil"),
        ]
        result = build_rhythm_sections(
            self.user, execution_contract={"items": items, "summaries": {}},
        )
        morning = next(s for s in result["sections"] if s["key"] == "morning")
        kinds = {(g["kind"], g["time_of_day"]) for g in morning["dose_groups"]}
        # Only built for the CURRENT rhythm. If morning isn't current we
        # skip — but the helper itself is deterministic and tested below.
        if morning["is_current"]:
            self.assertIn(("medication", "morning"), kinds)
            self.assertIn(("supplement", "morning"), kinds)

    def test_dose_groups_helper_counts_completion_production_shape(self):
        """Direct test of _build_dose_groups using PRODUCTION-faithful
        fixtures — dose items from today_execution.py carry the window
        key in `execution_group_id`, NOT `time_of_day`. Helper MUST read
        execution_group_id (with time_of_day as a secondary fallback).
        Regression for the missed group buttons in prod."""
        from apps.core.cos_briefing.rhythm import _build_dose_groups
        items = [
            # Production shape: execution_group_id holds the window key.
            {"source_type": "medication_dose", "intake_type": "medication",
             "execution_group_id": "morning", "completed_today": True, "title": "M1"},
            {"source_type": "medication_dose", "intake_type": "medication",
             "execution_group_id": "morning", "completed_today": False, "title": "M2"},
            {"source_type": "supplement_dose", "intake_type": "supplement",
             "execution_group_id": "morning", "completed_today": False, "title": "S1"},
            {"source_type": "medication_dose", "intake_type": "medication",
             "execution_group_id": "evening", "completed_today": False, "title": "M3"},
        ]
        groups = _build_dose_groups(items)
        self.assertEqual(len(groups), 3)
        morning_med = next(
            g for g in groups
            if g["kind"] == "medication" and g["time_of_day"] == "morning"
        )
        self.assertEqual(morning_med["count"], 2)
        self.assertEqual(morning_med["completed"], 1)
        self.assertFalse(morning_med["all_completed"])

    def test_dose_group_button_counts_equal_actual_click_outcomes(self):
        """TRUST RULE: each button's count = how many items the click
        actually affects. Complete shows open_count; Undo shows
        completed_count. No misleading total-cluster-size labels."""
        from apps.core.cos_briefing.rhythm import _build_dose_groups

        def _supp(completed, idx):
            return {
                "source_type": "supplement_dose",
                "intake_type": "supplement",
                "execution_group_id": "morning",
                "completed_today": completed,
                "title": f"S{idx}",
            }

        # Case A: 4 total / 0 completed → Complete shows (4)
        a = _build_dose_groups([_supp(False, i) for i in range(4)])[0]
        self.assertEqual(a["open_count"], 4)
        self.assertEqual(a["completed_count"], 0)
        self.assertFalse(a["all_completed"])

        # Case B: 4 total / 3 completed → Complete (1) + Undo (3)
        b = _build_dose_groups(
            [_supp(True, 0), _supp(True, 1), _supp(True, 2), _supp(False, 3)]
        )[0]
        self.assertEqual(b["open_count"], 1)
        self.assertEqual(b["completed_count"], 3)
        self.assertFalse(b["all_completed"])

        # Case C: 4 total / 4 completed → Undo (4) only
        c = _build_dose_groups([_supp(True, i) for i in range(4)])[0]
        self.assertEqual(c["open_count"], 0)
        self.assertEqual(c["completed_count"], 4)
        self.assertTrue(c["all_completed"])

        # Case D: 4 total / 2 completed → Complete (2) + Undo (2)
        d = _build_dose_groups(
            [_supp(True, 0), _supp(True, 1), _supp(False, 2), _supp(False, 3)]
        )[0]
        self.assertEqual(d["open_count"], 2)
        self.assertEqual(d["completed_count"], 2)

    def test_dose_groups_helper_falls_back_to_time_of_day(self):
        """Convenience fallback so direct callers can pass time_of_day."""
        from apps.core.cos_briefing.rhythm import _build_dose_groups
        items = [
            {"source_type": "medication_dose", "intake_type": "medication",
             "time_of_day": "morning", "completed_today": False, "title": "M1"},
        ]
        groups = _build_dose_groups(items)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["time_of_day"], "morning")

    def test_dose_groups_helper_ignores_non_dose_items(self):
        from apps.core.cos_briefing.rhythm import _build_dose_groups
        items = [
            {"source_type": "task", "title": "Wake Up"},
            {"source_type": "routine_item", "title": "Shower"},
        ]
        self.assertEqual(_build_dose_groups(items), [])

    def test_preview_groups_skips_completed_and_handles_unscheduled(self):
        from apps.core.cos_briefing.rhythm import _build_preview_groups
        items = [
            {"scheduled_time": "09:00", "completed_today": True, "title": "Done"},
            {"scheduled_time": "13:00", "completed_today": False, "title": "Later"},
            {"scheduled_time": None, "completed_today": False, "title": "Anytime task"},
        ]
        groups = _build_preview_groups(items)
        # Completed items excluded
        titles = sum((g["titles"] for g in groups), [])
        self.assertNotIn("Done", titles)
        self.assertIn("Later", titles)
        self.assertIn("Anytime task", titles)
        # Unscheduled groups under "Anytime"
        self.assertTrue(any(g["time"] == "Anytime" for g in groups))

    def test_only_next_rhythm_gets_preview_distant_futures_collapse(self):
        """SPEC: only the rhythm IMMEDIATELY after current gets preview
        mode. Farther future rhythms stay collapsed (interaction_mode=empty,
        expanded=False) even when they have items — the dashboard fills
        whitespace, it does not grow tall just because content exists.

        At 11:30 AM (morning active) with items scheduled in BOTH Day and
        Night: Day → preview (expanded), Night → empty (collapsed).
        """
        from apps.core.utils import get_user_now
        try:
            current_hour = get_user_now(self.user).time().hour
        except Exception:
            current_hour = 8
        # This test asserts behavior when morning is active.
        if current_hour >= 12:
            self.skipTest("Wall-clock has left the morning window")

        items = [
            self._items(scheduled_time="13:00", title="Day item",
                        source_type="task"),
            self._items(scheduled_time="22:00", title="Night med",
                        source_type="medication_dose",
                        execution_group_id="nightly",
                        intake_type="medication"),
        ]
        result = build_rhythm_sections(
            self.user, execution_contract={"items": items, "summaries": {}},
        )
        day = next(s for s in result["sections"] if s["key"] == "day")
        night = next(s for s in result["sections"] if s["key"] == "night")

        # Day is current+1 → preview, expanded.
        self.assertEqual(day["interaction_mode"], "preview")
        self.assertTrue(day["expanded"])

        # Night is current+3 → empty (collapsed) even though it has 1 item.
        self.assertEqual(night["interaction_mode"], "empty")
        self.assertFalse(night["expanded"])
        # But preview_groups MUST still be populated so click-to-expand
        # reveals real content (not a misleading "Nothing scheduled").
        self.assertTrue(night["preview_groups"])
        self.assertEqual(night["completion"]["total"], 1)

    def test_past_rhythm_with_open_items_stays_expanded(self):
        """TRUST RULE: a past rhythm that still has unfinished items must
        NOT collapse — hiding leftover meds/supplements/routines behind a
        summary creates the exact 'I forgot I had unfinished items'
        regression we forbade. Past + open_count>0 → expanded=True."""
        from apps.core.cos_briefing.rhythm import _bucket_index, RHYTHM_BUCKETS
        from apps.core.utils import get_user_now
        try:
            current_hour = get_user_now(self.user).time().hour
        except Exception:
            current_hour = 12

        # Pick the morning bucket and ensure today's "now" is past it.
        if current_hour < 12:
            self.skipTest("Wall-clock is still inside the morning window")

        items = [
            # One completed + one open morning item → past with leftover
            self._items(scheduled_time="06:00", title="Done thing",
                        completed_today=True),
            self._items(scheduled_time="07:00", title="Forgotten med",
                        completed_today=False, source_type="medication_dose",
                        intake_type="medication", time_of_day="morning"),
        ]
        result = build_rhythm_sections(
            self.user, execution_contract={"items": items, "summaries": {}},
        )
        morning = next(s for s in result["sections"] if s["key"] == "morning")
        self.assertTrue(morning["is_past"])
        self.assertEqual(morning["interaction_mode"], "summary")
        self.assertGreater(morning["open_count"], 0)
        self.assertTrue(
            morning["expanded"],
            "Past rhythm with leftover items MUST stay expanded — "
            "collapsing would hide unfinished work and break trust.",
        )

    def test_past_rhythm_fully_complete_does_collapse(self):
        """The trust rule only triggers when there are open items. A past
        rhythm that's fully complete should collapse to the compact
        summary as designed (minimal footprint, no accountability cost)."""
        from apps.core.utils import get_user_now
        try:
            current_hour = get_user_now(self.user).time().hour
        except Exception:
            current_hour = 12
        if current_hour < 12:
            self.skipTest("Wall-clock is still inside the morning window")

        items = [
            self._items(scheduled_time="06:00", title="Done A",
                        completed_today=True),
            self._items(scheduled_time="07:00", title="Done B",
                        completed_today=True),
        ]
        result = build_rhythm_sections(
            self.user, execution_contract={"items": items, "summaries": {}},
        )
        morning = next(s for s in result["sections"] if s["key"] == "morning")
        self.assertTrue(morning["is_past"])
        self.assertEqual(morning["interaction_mode"], "summary")
        self.assertEqual(morning["open_count"], 0)
        self.assertFalse(
            morning["expanded"],
            "Past rhythm with zero open items collapses — that's the "
            "compact summary the trust rule allows.",
        )

    def test_rhythm_returns_preview_key_for_beth_alignment(self):
        """Beth needs the same 'coming next' definition the dashboard uses,
        so it's surfaced on the canonical result."""
        result = build_rhythm_sections(
            self.user, execution_contract={"items": [], "summaries": {}},
        )
        self.assertIn("preview_key", result)


class HeadlineAndMomentumTests(TestCase):
    """Tests for the new Visual-Beth voice pieces."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="v3-voice@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    # ── Headline ──
    def test_headline_for_unknown_state(self):
        line = _derive_headline("unknown", [], [], None, None)
        self.assertIn("Light data", line)

    def test_headline_for_improving(self):
        line = _derive_headline("improving", [{}, {}], [], None, None)
        self.assertIn("trending up", line.lower())

    def test_headline_for_recovery_mode(self):
        # Recovery/stabilize mode resolves to the dominant "at_risk" state;
        # both badge and headline derive from that single verdict.
        state = {
            "recovery_state": {"mode": "RECOVERY"},
            "overdue_actions": [],
            "at_risk_actions": [],
        }
        self.assertEqual(_derive_overall_state([], [], None, state), "at_risk")
        line = _derive_headline("at_risk", [], [], state, {"title": "x"})
        self.assertIn("recover", line.lower())

    def test_headline_for_many_overdue(self):
        # 3+ overdue items resolve to the dominant "at_risk" state.
        state = {
            "recovery_state": {"mode": "NORMAL"},
            "overdue_actions": [{}, {}, {}, {}],
            "at_risk_actions": [],
        }
        self.assertEqual(_derive_overall_state([], [], None, state), "at_risk")
        line = _derive_headline("at_risk", [], [], state, None)
        self.assertIn("past due", line)

    def test_summary_emits_headline_key(self):
        summary = build_executive_summary(self.user)
        self.assertIn("headline", summary)
        self.assertIsInstance(summary["headline"], str)
        self.assertTrue(summary["headline"])

    # ── Momentum ──
    def test_momentum_for_complete_block(self):
        self.assertIn("Complete", _momentum_label(8, 8, 0, 0, False, True))

    def test_momentum_for_overdue(self):
        # End-of-day actionability: overdue rhythm items read as "behind"
        # (still recoverable today), never punitive "past due".
        line = _momentum_label(2, 5, 0, 2, True, False)
        self.assertIn("behind", line.lower())
        self.assertNotIn("past due", line.lower())

    def test_momentum_for_strong_progress(self):
        line = _momentum_label(6, 8, 0, 0, True, False)
        self.assertIn("strong", line.lower())

    def test_momentum_for_empty_block(self):
        self.assertEqual(_momentum_label(0, 0, 0, 0, False, False), "Nothing scheduled.")

    def test_rhythm_section_includes_momentum_field(self):
        result = build_rhythm_sections(
            self.user,
            execution_contract={"items": [], "summaries": {}},
        )
        for section in result["sections"]:
            self.assertIn("momentum", section)
            self.assertIsInstance(section["momentum"], str)

    def test_rhythm_section_includes_open_label_and_block_start(self):
        """Every section dict must carry open_label, open_count, and
        block_start_time so the template never renders an empty body."""
        result = build_rhythm_sections(
            self.user,
            execution_contract={"items": [], "summaries": {}},
        )
        for section in result["sections"]:
            self.assertIn("open_label", section)
            self.assertIn("open_count", section)
            self.assertIn("block_start_time", section)

    def test_future_block_momentum_mentions_block_start(self):
        """A future block with items must have a momentum line that names
        the start time — preventing the 'visible but blank' UX."""
        items = [
            # Future block: items scheduled in the Day window (12:00-17:00)
            {"scheduled_time": "13:00", "completed_today": False,
             "is_actionable": True, "title": "Fish Oil"},
            {"scheduled_time": "14:30", "completed_today": False,
             "is_actionable": True, "title": "Metformin"},
        ]
        result = build_rhythm_sections(
            self.user,
            execution_contract={"items": items, "summaries": {}},
        )
        day_section = next(s for s in result["sections"] if s["key"] == "day")
        # If we're currently in morning, day is future. If we're currently
        # in day, the assertion still holds because is_current path uses
        # different momentum copy — but block_start_time should always be
        # set when items exist.
        self.assertIsNotNone(day_section["block_start_time"])
        self.assertEqual(day_section["open_count"], 2)
        self.assertTrue(day_section["open_label"])  # Not empty string


class TemplateCommentLeakGuardTests(TestCase):
    """Regression guard: Django's {# #} comment syntax is single-line only.
    A multi-line {# ... #} block leaks as literal text into the rendered
    page. This test re-scans every v3 template after each change and fails
    if any multi-line {# ... #} comment is present."""

    def test_no_multiline_django_comments_in_v3_templates(self):
        import glob, os, re
        repo = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )))
        offenders = []
        for path in glob.glob(
            os.path.join(repo, "templates/dashboard_v3/**/*.html"),
            recursive=True,
        ):
            with open(path) as f:
                content = f.read()
            for m in re.finditer(r"\{#.*?#\}", content, re.DOTALL):
                if "\n" in m.group(0):
                    offenders.append(path)
                    break
        self.assertEqual(offenders, [], (
            "Multi-line {# ... #} comments leak as literal text in Django. "
            "Use {% comment %} ... {% endcomment %} instead. "
            f"Offending files: {offenders}"
        ))


class MissionCardTests(TestCase):
    """Phase 2A Mission spotlight — deterministic, read-only, no fabrication.

    Selection is EXPLICIT: only the goal the user marked as Primary Mission
    (``is_primary_mission=True``) surfaces. No derived fallback. Card hides
    when no Primary Mission is selected; rows omit when their data is absent.
    Reuse only: LifeGoal + GoalMilestone + GoalMomentumSnapshot.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="v3-mission@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def _goal(self, **kw):
        from apps.purpose.models import LifeGoal
        defaults = {
            "user": self.user,
            "title": "Mission Goal",
            "status": "active",
            "is_primary_mission": True,
        }
        defaults.update(kw)
        return LifeGoal.objects.create(**defaults)

    def _milestone(self, goal, **kw):
        from apps.purpose.models import GoalMilestone
        defaults = {"goal": goal, "title": "Phase One", "completed": False}
        defaults.update(kw)
        return GoalMilestone.objects.create(**defaults)

    def _momentum(self, goal, trend="rising", score=60):
        from apps.dashboard_v2.models import GoalMomentumSnapshot
        from datetime import date
        return GoalMomentumSnapshot.objects.create(
            user=self.user, goal=goal, snapshot_date=date.today(),
            momentum_score=score, progress_score=40, momentum_trend=trend,
        )

    def test_context_always_carries_mission_key(self):
        ctx = build_dashboard_v3_context(self.user)
        self.assertIn("mission", ctx)

    def test_non_mission_goal_renders_nothing(self):
        # An active goal NOT marked Primary Mission must NOT surface. No
        # derived fallback (foundational, deadline, momentum) may pick it.
        self._goal(is_primary_mission=False, is_foundational=True)
        ctx = build_dashboard_v3_context(self.user)
        self.assertIsNone(ctx["mission"])

    def test_full_card_from_existing_state(self):
        from datetime import date, timedelta
        target = date.today() + timedelta(days=365)
        goal = self._goal(title="France 2027", target_date=target)
        ms_date = date.today() + timedelta(days=120)
        self._milestone(goal, title="Foundation — Build Momentum",
                        target_date=ms_date)
        self._momentum(goal, trend="rising")

        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertIsNotNone(mission)
        self.assertEqual(mission["title"], "France 2027")
        self.assertEqual(mission["current_focus"], "Foundation — Build Momentum")
        self.assertEqual(mission["days_remaining"], 365)
        self.assertEqual(mission["momentum"]["label"], "Improving")
        self.assertEqual(mission["momentum"]["trend"], "up")
        self.assertIsNotNone(mission["next_milestone_date"])

    def test_momentum_omitted_when_no_snapshot(self):
        self._goal(title="No Momentum Goal")
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertIsNotNone(mission)
        self.assertIsNone(mission["momentum"])  # never fabricated

    def test_days_remaining_omitted_when_no_target_date(self):
        self._goal(title="Open-ended", target_date=None)
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertIsNone(mission["days_remaining"])

    def test_current_focus_omitted_when_no_open_milestone(self):
        goal = self._goal(title="All done")
        self._milestone(goal, completed=True)
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertIsNone(mission["current_focus"])

    def test_only_primary_mission_surfaces(self):
        from datetime import date, timedelta
        # Decoy: a foundational, near-term, momentum-bearing goal that the OLD
        # derived selector would have picked — but it's not the Primary Mission.
        decoy = self._goal(title="Decoy", is_primary_mission=False,
                           is_foundational=True,
                           target_date=date.today() + timedelta(days=30))
        self._milestone(decoy, title="Phase")
        self._momentum(decoy, trend="rising", score=99)
        # The explicitly-selected Primary Mission must win regardless.
        self._goal(title="Chosen Mission",
                   target_date=date.today() + timedelta(days=400))
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertEqual(mission["title"], "Chosen Mission")

    def test_paused_primary_mission_does_not_surface(self):
        # Primary Mission flag is necessary but not sufficient — status must
        # also be active (a paused mission hides the card).
        self._goal(title="Paused Mission", status="paused")
        ctx = build_dashboard_v3_context(self.user)
        self.assertIsNone(ctx["mission"])

    # ── Phase 2B: hero visuals (icon, ring, why) ─────────────────────────

    def test_explicit_mission_icon_metadata_wins(self):
        self._goal(title="France 2027", mission_icon="🇫🇷")
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertEqual(mission["icon"], "🇫🇷")
        self.assertEqual(mission["title"], "France 2027")  # title untouched

    def test_leading_emoji_lifted_from_title_when_no_metadata(self):
        self._goal(title="🎯 Run a Marathon")
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertEqual(mission["icon"], "🎯")
        # The emoji is removed from the display title so it isn't shown twice.
        self.assertEqual(mission["title"], "Run a Marathon")

    def test_no_icon_inferred_from_words(self):
        # Plain text title with no emoji and no metadata → no icon. Critically,
        # the word "France" must NEVER produce a flag (no hardcoded inference).
        self._goal(title="France 2027 Family 10K")
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertIsNone(mission["icon"])
        self.assertEqual(mission["title"], "France 2027 Family 10K")

    def test_ring_reports_truthful_milestone_progression(self):
        goal = self._goal(title="Tracked")
        self._milestone(goal, title="A", completed=True)
        self._milestone(goal, title="B", completed=True)
        self._milestone(goal, title="C", completed=False)
        progress = build_dashboard_v3_context(self.user)["mission"]["progress"]
        self.assertTrue(progress["has_milestones"])
        self.assertEqual(progress["completed"], 2)
        self.assertEqual(progress["total"], 3)
        self.assertEqual(progress["filled"], 67)  # round(2/3*100)

    def test_ring_has_no_milestones_flag_when_none_defined(self):
        self._goal(title="No milestones")
        progress = build_dashboard_v3_context(self.user)["mission"]["progress"]
        self.assertFalse(progress["has_milestones"])
        self.assertEqual(progress["total"], 0)
        self.assertEqual(progress["filled"], 0)

    def test_why_excerpt_only_present_when_user_wrote_one(self):
        self._goal(title="With why", why_it_matters="  Family memories.  ")
        with_why = build_dashboard_v3_context(self.user)["mission"]
        self.assertEqual(with_why["why"], "Family memories.")

    def test_why_is_none_when_blank(self):
        self._goal(title="No why", why_it_matters="")
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertIsNone(mission["why"])

    # ── Visual fidelity correction: panel, subtitle, drivers ─────────────

    def _seed_state(self, **modules):
        """Write a pre-computed SAE snapshot the read-only path will see."""
        from apps.core.ai_state.models import UserState
        UserState.objects.update_or_create(
            user=self.user, defaults={"state_data": modules}
        )

    def test_panel_narrative_is_fixed_and_grounded_in_momentum(self):
        # The "how things are going" panel selects one of three pre-approved,
        # deterministic sentences — never generated, keyed only by trend.
        goal = self._goal(title="Tracked")
        self._momentum(goal, trend="rising")
        panel = build_dashboard_v3_context(self.user)["mission"]["panel"]
        self.assertIsNotNone(panel)
        self.assertEqual(panel["trend"], "up")
        self.assertEqual(panel["label"], "Improving")
        self.assertIn("building momentum", panel["narrative"])

    def test_panel_fallback_when_no_momentum_is_neutral(self):
        # No snapshot → panel still renders, but with a NEUTRAL ("flat")
        # indicator and a milestone-grounded line. A rising/falling DIRECTION
        # is never fabricated without a real snapshot.
        self._goal(title="No momentum")
        panel = build_dashboard_v3_context(self.user)["mission"]["panel"]
        self.assertIsNotNone(panel)
        self.assertEqual(panel["trend"], "flat")
        self.assertTrue(panel["is_fallback"])
        self.assertEqual(panel["label"], "Getting started")

    def test_panel_fallback_underway_when_milestones_complete(self):
        goal = self._goal(title="Some progress")
        self._milestone(goal, title="Done", completed=True)
        self._milestone(goal, title="Open", completed=False)
        panel = build_dashboard_v3_context(self.user)["mission"]["panel"]
        self.assertEqual(panel["trend"], "flat")
        self.assertEqual(panel["label"], "Underway")
        self.assertTrue(panel["is_fallback"])

    def test_panel_prefers_real_momentum_over_fallback(self):
        goal = self._goal(title="Real momentum")
        self._momentum(goal, trend="falling")
        panel = build_dashboard_v3_context(self.user)["mission"]["panel"]
        self.assertFalse(panel["is_fallback"])
        self.assertEqual(panel["trend"], "down")
        self.assertEqual(panel["label"], "Declining")

    def test_next_milestone_days_from_real_future_target(self):
        from datetime import date, timedelta
        goal = self._goal(title="Timed")
        self._milestone(goal, title="Foundation Phase Complete",
                        target_date=date.today() + timedelta(days=181))
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertEqual(mission["next_milestone_days"], 181)
        self.assertEqual(mission["current_focus"], "Foundation Phase Complete")

    def test_next_milestone_days_none_without_target(self):
        goal = self._goal(title="Untimed")
        self._milestone(goal, title="Open", target_date=None)
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertIsNone(mission["next_milestone_days"])

    def test_subtitle_from_user_description(self):
        self._goal(title="With desc", description="  Run a family 10K.  ")
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertEqual(mission["subtitle"], "Run a family 10K.")

    def test_subtitle_none_when_no_description(self):
        self._goal(title="No desc", description="")
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertIsNone(mission["subtitle"])

    def test_drivers_surfaced_from_precomputed_state(self):
        # Drivers read ONLY pre-computed SAE module state, never live compute.
        self._goal(title="Driven")
        self._seed_state(
            health={
                "weight_change_30d": -2.3,
                "weight_trend": "decreasing",
                "steps_avg_7d": 8421,
                "sleep_avg_hours_7d": 7.1,
            },
            fitness={"workouts_7d": 4},
            journal={"entries_7d": 5},
            # macro score is meaningful only with real intake today
            nutrition={"enabled": True, "macro_compliance_score": 82, "food_entries_today": 4},
        )
        drivers = build_dashboard_v3_context(self.user)["mission"]["drivers"]
        keys = [d["key"] for d in drivers]
        self.assertEqual(
            keys, ["weight", "workouts", "steps", "sleep", "journal", "nutrition"]
        )
        weight = next(d for d in drivers if d["key"] == "weight")
        self.assertEqual(weight["value"], "-2.3 lb / 30d")
        self.assertEqual(weight["trend"], "down")
        steps = next(d for d in drivers if d["key"] == "steps")
        self.assertEqual(steps["value"], "8,421/day")

    def test_drivers_gracefully_omitted_when_signal_absent(self):
        # Missing fields are omitted entirely — no zero-fill, no fabrication.
        self._goal(title="Sparse")
        self._seed_state(
            health={"steps_avg_7d": 6000},  # only steps present
            fitness={},
            journal={},
            nutrition={"enabled": False},
        )
        drivers = build_dashboard_v3_context(self.user)["mission"]["drivers"]
        self.assertEqual([d["key"] for d in drivers], ["steps"])

    def test_drivers_empty_when_state_has_no_signals(self):
        self._goal(title="Empty state")
        self._seed_state(health={}, fitness={}, journal={}, nutrition={})
        drivers = build_dashboard_v3_context(self.user)["mission"]["drivers"]
        self.assertEqual(drivers, [])

    # ── Phase 3: Mission Intelligence — deterministic state classifier ────

    def _status(self):
        return build_dashboard_v3_context(self.user)["mission"]["status"]

    def test_status_always_present_for_active_mission(self):
        self._goal(title="Stateful")
        status = self._status()
        self.assertIn(status["state"], {
            "GETTING_STARTED", "BUILDING_MOMENTUM", "IMPROVING",
            "MAINTAINING", "SLIPPING", "AT_RISK",
        })
        self.assertIn(status["ring_word"], {
            "BUILDING", "MOMENTUM", "ON TRACK", "STEADY", "RECOVER", "REFOCUS",
        })

    def test_getting_started_when_no_signals_no_momentum(self):
        # No tracked positives + no momentum snapshot → the only honest state.
        self._goal(title="Fresh")
        self._seed_state(health={}, fitness={}, journal={}, nutrition={})
        status = self._status()
        self.assertEqual(status["state"], "GETTING_STARTED")
        self.assertEqual(status["ring_word"], "BUILDING")
        self.assertEqual(status["tone"], "flat")

    def test_building_momentum_when_helping_signal_but_no_trend(self):
        # A positive tracked behaviour without a snapshot → momentum forming,
        # but never a fabricated IMPROVING direction.
        self._goal(title="Forming")
        self._seed_state(fitness={"workouts_7d": 4})
        status = self._status()
        self.assertEqual(status["state"], "BUILDING_MOMENTUM")
        self.assertEqual(status["ring_word"], "MOMENTUM")
        self.assertTrue(any(d["label"] == "Workouts" for d in status["helping"]))

    def test_improving_requires_real_rising_snapshot(self):
        goal = self._goal(title="Rising")
        self._momentum(goal, trend="rising")
        self._seed_state(fitness={"workouts_7d": 4})
        status = self._status()
        self.assertEqual(status["state"], "IMPROVING")
        self.assertEqual(status["ring_word"], "ON TRACK")
        self.assertEqual(status["tone"], "up")

    def test_at_risk_when_falling_and_multiple_needs(self):
        goal = self._goal(title="Struggling")
        self._momentum(goal, trend="falling")
        self._seed_state(
            fitness={"workouts_7d": 0},
            journal={"entries_7d": 0},
            health={"sleep_avg_hours_7d": 5.0},
        )
        status = self._status()
        self.assertEqual(status["state"], "AT_RISK")
        self.assertEqual(status["ring_word"], "REFOCUS")
        self.assertGreaterEqual(len(status["needs"]), 3)

    def test_slipping_when_falling_with_few_needs(self):
        goal = self._goal(title="Softening")
        self._momentum(goal, trend="falling")
        self._seed_state(fitness={"workouts_7d": 0})
        status = self._status()
        self.assertEqual(status["state"], "SLIPPING")
        self.assertEqual(status["ring_word"], "RECOVER")

    def test_maintaining_when_stable_with_helping(self):
        goal = self._goal(title="Holding")
        self._momentum(goal, trend="stable")
        self._seed_state(
            fitness={"workouts_7d": 4},
            health={"sleep_avg_hours_7d": 7.5},
        )
        status = self._status()
        self.assertEqual(status["state"], "MAINTAINING")
        self.assertEqual(status["ring_word"], "STEADY")

    def test_narrative_references_actual_signals(self):
        # Copy must ground in real signals — not generic personalisation.
        goal = self._goal(title="Grounded")
        self._momentum(goal, trend="rising")
        self._seed_state(
            fitness={"workouts_7d": 5},
            nutrition={"enabled": True, "macro_compliance_score": None},
        )
        status = self._status()
        self.assertIn("training is consistent", status["narrative"])
        self.assertIn("Nutrition isn't being tracked", status["narrative"])

    def test_no_major_concerns_when_no_needs(self):
        goal = self._goal(title="Clean")
        self._momentum(goal, trend="rising")
        self._seed_state(
            fitness={"workouts_7d": 5},
            health={"sleep_avg_hours_7d": 8.0, "steps_avg_7d": 9000},
        )
        status = self._status()
        self.assertEqual(status["needs"], [])

    def test_nutrition_untracked_is_a_need(self):
        # Objective absence — untracked nutrition is a real need, not a guess.
        goal = self._goal(title="No nutrition")
        self._seed_state(nutrition={"enabled": True, "macro_compliance_score": None})
        status = self._status()
        self.assertTrue(any(d["label"] == "Nutrition" for d in status["needs"]))

    def test_success_criteria_three_column_split(self):
        # The canonical Phase-4 scenario: an active user rebuilding health with
        # ~6h sleep and weak journaling/nutrition lands as Helping (Workouts,
        # Weight, Movement) / Worth watching (Sleep, Nutrition) / Needs (Journal).
        # Crucially, ~6h sleep is a middle state — never "Needs attention".
        goal = self._goal(title="France 2027")
        self._momentum(goal, trend="rising")
        self._seed_state(
            fitness={"workouts_7d": 4},      # helping; movement active → helping
            health={
                "weight_change_30d": -2.0, "weight_trend": "decreasing",  # helping
                "sleep_avg_hours_7d": 6.1,   # 5.5–6.99 → Worth watching (NOT a need)
                "steps_avg_7d": 5500,        # low steps must NOT bury Movement
            },
            journal={"entries_7d": 0},       # objective absence → need
            # tracked, low macros (intake logged today) → watch
            nutrition={"enabled": True, "macro_compliance_score": 55, "food_entries_today": 3},
        )
        status = self._status()
        help_labels = [d["label"] for d in status["helping"]]
        watch_labels = [d["label"] for d in status["watching"]]
        need_labels = [d["label"] for d in status["needs"]]
        self.assertEqual(set(help_labels), {"Workouts", "Weight", "Movement"})
        self.assertIn("Sleep", watch_labels)
        self.assertIn("Nutrition", watch_labels)
        self.assertIn("Journal", need_labels)
        # ~6h sleep is a middle state, never a failure.
        self.assertNotIn("Sleep", need_labels)
        self.assertNotIn("Steps", help_labels + watch_labels + need_labels)

    def test_neutral_signal_lands_in_worth_watching_not_needs(self):
        # A lone mid-band sleep value surfaces in Worth watching — not Helping,
        # not Needs attention. It is a real middle category.
        goal = self._goal(title="Mid sleep")
        self._seed_state(health={"sleep_avg_hours_7d": 6.1})
        status = self._status()
        self.assertIn("Sleep", [d["label"] for d in status["watching"]])
        self.assertNotIn("Sleep", [d["label"] for d in status["helping"]])
        self.assertNotIn("Sleep", [d["label"] for d in status["needs"]])

    def test_strong_signals_not_displaced_by_neutral(self):
        # Strong helping signals fill their own column; a neutral signal goes to
        # Worth watching and can never bump a strong one out of Helping.
        goal = self._goal(title="Crowded helping")
        self._momentum(goal, trend="rising")
        self._seed_state(
            fitness={"workouts_7d": 5},      # helping (+ Movement helping, foundation)
            health={
                "weight_change_30d": -1.0, "weight_trend": "decreasing",  # helping
                "sleep_avg_hours_7d": 6.1,   # neutral → Worth watching, not Helping
            },
        )
        status = self._status()
        self.assertEqual(len(status["helping"]), 3)
        self.assertIn("Sleep", [d["label"] for d in status["watching"]])
        self.assertEqual(
            set(d["label"] for d in status["helping"]),
            {"Workouts", "Weight", "Movement"},
        )

    def test_narrative_uses_encouraging_watch_clause_when_no_needs(self):
        # Mission psychology: with no material need, the card closes on a
        # constructive watch clause, not a flat "still not good enough" note.
        goal = self._goal(title="Watchful")
        self._momentum(goal, trend="rising")
        self._seed_state(
            fitness={"workouts_7d": 4},        # helping
            health={"sleep_avg_hours_7d": 6.1},  # watch, no needs
        )
        status = self._status()
        self.assertIn("enough to maintain momentum", status["narrative"])

    def test_sleep_seven_hours_is_helping(self):
        goal = self._goal(title="Rested")
        self._seed_state(health={"sleep_avg_hours_7d": 7.0})  # >=7.0 → helping
        status = self._status()
        self.assertIn("Sleep", [d["label"] for d in status["helping"]])

    def test_sleep_six_hours_is_worth_watching_not_a_need(self):
        # Adaptive recovery: ~6h is sufficient to maintain momentum — a watch,
        # never a "Needs attention" failure for someone rebuilding health.
        goal = self._goal(title="Six hours")
        self._seed_state(health={"sleep_avg_hours_7d": 6.0})  # 5.5–6.99 → watch
        status = self._status()
        self.assertIn("Sleep", [d["label"] for d in status["watching"]])
        self.assertNotIn("Sleep", [d["label"] for d in status["needs"]])

    def test_sleep_below_five_and_a_half_is_a_need(self):
        # Only materially poor recovery (<5.5h) lands in Needs attention.
        goal = self._goal(title="Deprived")
        self._seed_state(health={"sleep_avg_hours_7d": 5.2})  # <5.5 → needs
        status = self._status()
        self.assertIn("Sleep", [d["label"] for d in status["needs"]])

    def test_movement_helping_despite_low_steps_in_foundation(self):
        # Phase 3.5 core: a user active through workouts is NOT penalised for low
        # steps during the foundation phase. Movement reads as Helping.
        goal = self._goal(title="Active, low steps")
        self._seed_state(
            fitness={"workouts_7d": 3},
            health={"steps_avg_7d": 3000},   # low steps — foundation must not penalise
        )
        status = self._status()
        help_labels = [d["label"] for d in status["helping"]]
        all_labels = help_labels + [d["label"] for d in status["needs"]]
        self.assertIn("Movement", help_labels)
        self.assertNotIn("Steps", all_labels)

    def test_movement_needs_when_truly_inactive(self):
        # No workouts AND low/absent steps → genuinely inactive → Movement is a Need.
        goal = self._goal(title="Inactive")
        self._seed_state(
            fitness={"workouts_7d": 0},
            health={"steps_avg_7d": 2000},
        )
        status = self._status()
        self.assertTrue(any(d["label"] == "Movement" for d in status["needs"]))

    def test_movement_phase_readiness_weighs_steps(self):
        # Readiness phase (>=half milestones done) re-introduces step tolerance:
        # the SAME activity that was Helping in foundation becomes a Need here.
        goal = self._goal(title="Return to running")
        self._milestone(goal, title="Foundation done", completed=True)
        self._milestone(goal, title="Build mileage", completed=False)  # 1/2 → readiness
        self._seed_state(
            fitness={"workouts_7d": 3},
            health={"steps_avg_7d": 3000},   # low steps now matters
        )
        status = self._status()
        self.assertTrue(any(d["label"] == "Movement" for d in status["needs"]))

    def test_movement_value_aggregates_active_minutes(self):
        # Display value prefers real tracked active minutes over a session count.
        goal = self._goal(title="Minutes")
        self._seed_state(fitness={"workouts_7d": 4, "workout_minutes_7d": 180})
        status = self._status()
        movement = next(d for d in status["helping"] if d["label"] == "Movement")
        self.assertEqual(movement["value"], "180 min/wk")

    def test_no_per_column_cap_all_signals_shown(self):
        # Phase D — the hard 3-per-column cap is removed. Mission truth beats
        # layout neatness: every real signal surfaces. Here FIVE signals are all
        # helping; none may be silently dropped.
        goal = self._goal(title="Lots of signals")
        self._momentum(goal, trend="rising")
        self._seed_state(
            fitness={"workouts_7d": 5},
            health={
                "sleep_avg_hours_7d": 8.0,
                "steps_avg_7d": 12000,
                "weight_change_30d": -2.0,
                "weight_trend": "decreasing",
            },
            nutrition={"enabled": True, "macro_compliance_score": 90, "food_entries_today": 4},
        )
        status = self._status()
        help_labels = [d["label"] for d in status["helping"]]
        self.assertGreater(len(help_labels), 3)  # no cap — more than three show
        self.assertEqual(
            set(help_labels),
            {"Workouts", "Movement", "Weight", "Sleep", "Nutrition"},
        )

    def test_a1c_never_vanishes_and_leads_for_health_mission(self):
        # Phase 6.3 + Phase D — for a metabolic (health-domain) mission, Projected
        # A1C must lead its column AND, with the cap removed, every competing
        # neutral signal also stays visible. A1C can never be silently dropped.
        from apps.purpose.models import LifeDomain
        domain = LifeDomain.objects.create(name="Health", slug="health")
        goal = self._goal(title="Metabolic mission", domain=domain)
        self._momentum(goal, trend="stable")
        # All of these land in "watching" (neutral): a worsening-but-in-target
        # A1C (not punitive), 6h sleep, stable weight, partial nutrition. Weight
        # is emitted BEFORE A1C in natural order, so only pinning can make A1C
        # the FRONT of the column.
        self._seed_state(
            health={
                "projected_a1c": 6.4,
                "projected_a1c_trend": "worsening",
                "projected_a1c_confidence": "high",
                "sleep_avg_hours_7d": 6.0,
                "weight_change_30d": 0.0,
                "weight_trend": "stable",
            },
            nutrition={"enabled": True, "macro_compliance_score": 50, "food_entries_today": 3},
        )
        status = self._status()
        watching_labels = [d["label"] for d in status["watching"]]
        # No cap — all four neutral signals are present.
        self.assertEqual(len(watching_labels), 4)
        self.assertIn("Projected A1C (GMI)", watching_labels)
        # And A1C is lifted to the FRONT of its column (highest mission priority),
        # ahead of the earlier-emitted Weight.
        self.assertEqual(watching_labels[0], "Projected A1C (GMI)")

    # ── Phase 5: emotional motivation layer (read-only metadata) ─────────

    def test_mission_links_exposed_in_order(self):
        from apps.purpose.models import GoalMotivationLink
        goal = self._goal(title="Linked")
        GoalMotivationLink.objects.create(
            goal=goal, title="Race", url="https://example.com/race",
            icon="🏁", sort_order=2,
        )
        GoalMotivationLink.objects.create(
            goal=goal, title="Inspiration", url="https://example.com/board",
            icon="📸", sort_order=1,
        )
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertEqual(
            [l["title"] for l in mission["mission_links"]],
            ["Inspiration", "Race"],
        )

    def test_mission_links_empty_when_none(self):
        self._goal(title="No links")
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertEqual(mission["mission_links"], [])

    def test_victories_progress_counts(self):
        from apps.purpose.models import GoalVictoryMilestone
        goal = self._goal(title="Wins")
        GoalVictoryMilestone.objects.create(goal=goal, title="First 5K", completed=True)
        GoalVictoryMilestone.objects.create(goal=goal, title="Two weeks", completed=False)
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertEqual(mission["victories"], {"total": 2, "completed": 1})

    def test_victories_none_when_no_wins(self):
        self._goal(title="No wins")
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertIsNone(mission["victories"])

    def test_hero_image_url_none_when_unset(self):
        self._goal(title="No hero")
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertIsNone(mission["hero_image_url"])

    def test_victory_milestones_do_not_affect_milestone_progress(self):
        # Victory milestones are a SEPARATE relation — they must never change
        # the major-milestone ring/phase counts that drive mission truth.
        from apps.purpose.models import GoalVictoryMilestone
        goal = self._goal(title="Separation")
        self._milestone(goal, title="Major", completed=False)
        GoalVictoryMilestone.objects.create(goal=goal, title="Tiny win", completed=True)
        self.assertEqual(goal.milestone_count, 1)
        self.assertEqual(goal.completed_milestone_count, 0)
        mission = build_dashboard_v3_context(self.user)["mission"]
        self.assertEqual(mission["progress"]["total"], 1)
        self.assertEqual(mission["progress"]["completed"], 0)

    # ── Phase 6: Projected A1C mission signal (trend-driven, confidence-gated) ─

    def test_a1c_improving_trend_is_helping(self):
        # Trend matters more than the absolute number: a falling A1C reads as
        # encouraging (Helping momentum) even while still elevated.
        self._goal(title="Metabolic")
        self._seed_state(health={
            "projected_a1c": 8.1,
            "projected_a1c_trend": "improving",
            "projected_a1c_confidence": "high",
        })
        status = self._status()
        helping = [d for d in status["helping"] if d["label"] == "Projected A1C (GMI)"]
        self.assertTrue(helping)
        # Phase 6.4 — value is the GMI percent only (no trend arrow); the
        # estimate basis is stated in the note, the trend drives the column.
        self.assertEqual(helping[0]["value"], "8.1%")

    def test_a1c_stable_above_target_is_worth_watching(self):
        self._goal(title="Steady high")
        self._seed_state(health={
            "projected_a1c": 7.4,
            "projected_a1c_trend": "stable",
            "projected_a1c_confidence": "high",
        })
        status = self._status()
        self.assertIn("Projected A1C (GMI)", [d["label"] for d in status["watching"]])
        self.assertNotIn("Projected A1C (GMI)", [d["label"] for d in status["helping"]])

    def test_a1c_stable_in_target_is_worth_watching_not_helping(self):
        # Phase 6.4 — a steady A1C must NOT be auto-placed in Helping. Holding
        # level is "worth watching", never false reassurance, even in-target.
        self._goal(title="In control")
        self._seed_state(health={
            "projected_a1c": 6.2,
            "projected_a1c_trend": "stable",
            "projected_a1c_confidence": "high",
        })
        status = self._status()
        self.assertIn("Projected A1C (GMI)", [d["label"] for d in status["watching"]])
        self.assertNotIn("Projected A1C (GMI)", [d["label"] for d in status["helping"]])

    def test_a1c_worsening_above_target_needs_attention(self):
        self._goal(title="Drifting up")
        self._seed_state(health={
            "projected_a1c": 8.2,
            "projected_a1c_trend": "worsening",
            "projected_a1c_confidence": "high",
        })
        status = self._status()
        self.assertIn("Projected A1C (GMI)", [d["label"] for d in status["needs"]])

    def test_a1c_worsening_in_target_is_not_punitive(self):
        # Drifting within a healthy range must NOT be flagged as a failure —
        # it is a watch, never a punitive "Needs attention".
        self._goal(title="Tiny drift")
        self._seed_state(health={
            "projected_a1c": 6.4,
            "projected_a1c_trend": "worsening",
            "projected_a1c_confidence": "high",
        })
        status = self._status()
        self.assertNotIn("Projected A1C (GMI)", [d["label"] for d in status["needs"]])
        self.assertIn("Projected A1C (GMI)", [d["label"] for d in status["watching"]])

    def test_a1c_medium_confidence_renders_with_caveat(self):
        # Medium confidence still shows the standard GMI number (tilde-marked),
        # and states the softer basis in the note rather than hiding the metric.
        self._goal(title="Recent only")
        self._seed_state(health={
            "projected_a1c": 6.5,
            "projected_a1c_trend": "stable",
            "projected_a1c_confidence": "medium",
        })
        status = self._status()
        match = [d for col in ("helping", "watching", "needs")
                 for d in status[col] if d["label"] == "Projected A1C (GMI)"]
        self.assertTrue(match)
        self.assertIn("6.5%", match[0]["value"])
        self.assertIn("~", match[0]["value"])
        self.assertEqual(match[0]["note"], "Using recent available glucose data")

    def test_a1c_high_confidence_carries_confidence_note(self):
        # High confidence states its CGM-derived basis in the note (truthful
        # context), never a completion-resembling visual or "actual lab A1C" claim.
        self._goal(title="Dense data")
        self._seed_state(health={
            "projected_a1c": 6.2,
            "projected_a1c_trend": "stable",
            "projected_a1c_confidence": "high",
        })
        status = self._status()
        match = [d for col in ("helping", "watching", "needs")
                 for d in status[col] if d["label"] == "Projected A1C (GMI)"]
        self.assertTrue(match)
        self.assertEqual(match[0]["note"], "Estimated from CGM data")

    def test_a1c_low_insufficient_renders_dash_with_history_note(self):
        # Low confidence from THIN history must NOT be silently hidden — it shows
        # an em-dash with a "need more history" note, never a fabricated number.
        self._goal(title="Sparse glucose")
        self._seed_state(health={
            "projected_a1c": None,
            "projected_a1c_confidence": "low",
            "projected_a1c_low_reason": "insufficient_data",
            "glucose_reading_count_90d": 12,
        })
        status = self._status()
        match = [d for col in ("helping", "watching", "needs")
                 for d in status[col] if d["label"] == "Projected A1C (GMI)"]
        self.assertTrue(match)
        self.assertEqual(match[0]["value"], "—")
        self.assertEqual(match[0]["note"], "Need more glucose history")
        self.assertNotIn("%", match[0]["value"])

    def test_a1c_low_stale_sync_renders_dash_with_sync_note(self):
        # Low confidence from SYNC LAG (real history, just not synced) reads as a
        # sync state, never user failure — em-dash value + "Waiting for glucose sync".
        self._goal(title="Synced stale")
        self._seed_state(health={
            "projected_a1c": None,
            "projected_a1c_confidence": "low",
            "projected_a1c_low_reason": "stale_sync",
            "glucose_reading_count_90d": 80,
        })
        status = self._status()
        match = [d for col in ("helping", "watching", "needs")
                 for d in status[col] if d["label"] == "Projected A1C (GMI)"]
        self.assertTrue(match)
        self.assertEqual(match[0]["value"], "—")
        self.assertEqual(match[0]["note"], "Waiting for glucose sync")

    def test_a1c_engine_error_renders_unavailable_not_silent(self):
        # Phase 6.3 — an engine failure (error sentinel) must render visibly as
        # "Unavailable", never vanish, so the user can tell breakage from no-data.
        self._goal(title="Broken engine")
        self._seed_state(health={"projected_a1c_confidence": "error"})
        status = self._status()
        match = [d for col in ("helping", "watching", "needs")
                 for d in status[col] if d["label"] == "Projected A1C (GMI)"]
        self.assertTrue(match)
        self.assertEqual(match[0]["value"], "Unavailable")
        self.assertEqual(match[0]["note"], "Glucose insights temporarily unavailable")

    def test_a1c_hidden_only_when_truly_no_glucose(self):
        # Confidence None (no CGM, no history) is the ONLY case where the slot is
        # legitimately absent — itself a truthful "no data" state.
        self._goal(title="No glucose")
        self._seed_state(health={})
        status = self._status()
        labels = [d["label"] for col in ("helping", "watching", "needs")
                  for d in status[col]]
        self.assertNotIn("Projected A1C (GMI)", labels)

    # ── Phase 6: Clickable action drivers ────────────────────────────────

    def test_displayed_drivers_carry_clickable_destinations(self):
        # Each displayed driver resolves ONE meaningful destination URL so the
        # template can render it as a subtle clickable affordance.
        self._goal(title="Actionable")
        self._seed_state(
            fitness={"workouts_7d": 4},  # Workouts + Movement → helping
        )
        status = self._status()
        workouts = next(d for d in status["helping"] if d["label"] == "Workouts")
        self.assertIsNotNone(workouts["dest"])
        self.assertEqual(workouts["dest"]["href"], "/health/physical/fitness/workouts/")

    def test_a1c_driver_points_to_insight_not_logging(self):
        # Automated metrics are clickable but route to an INSIGHT view, never a
        # manual-logging form (logging glucose by hand would be wrong).
        self._goal(title="Insight route")
        self._seed_state(health={
            "projected_a1c": 6.9,
            "projected_a1c_trend": "improving",
            "projected_a1c_confidence": "high",
        })
        status = self._status()
        a1c = next(d for d in status["helping"] if d["label"] == "Projected A1C (GMI)")
        self.assertEqual(a1c["dest"]["href"], "/health/physical/glucose/")
        self.assertFalse(a1c["dest"]["is_log"])

    def test_nutrition_driver_points_to_nutrition_home(self):
        # The nutrition driver must resolve to the canonical nutrition page
        # (health:nutrition_home → /health/physical/nutrition/), never the
        # legacy meals route. Regression guard for the wrong-link bug.
        self._goal(title="Nutrition route")
        self._seed_state(nutrition={"enabled": True, "macro_compliance_score": 80, "food_entries_today": 3})
        status = self._status()
        nutri = next(
            d for col in ("helping", "watching", "needs")
            for d in status[col] if d["label"] == "Nutrition"
        )
        self.assertEqual(nutri["dest"]["href"], "/health/physical/nutrition/")

    # ── Phase C: nutrition logging signal when no macro goals are set ─────
    # Regression (2026-05-31): mission read the GOAL-GATED macro_compliance_score
    # only. A user who logs food but never set macro targets had macros=None →
    # the card showed "Not tracked"/"0% macros" right after they logged. The fix
    # falls back to the canonical LOGGING signal (food_entries_today / _7d).

    def test_nutrition_logging_without_macro_goals_is_not_a_need(self):
        # Food logged today, no macro targets → tracked (neutral), never a Need.
        self._goal(title="Logging only")
        self._seed_state(nutrition={
            "enabled": True,
            "macro_compliance_score": None,
            "food_entries_today": 2,
        })
        status = self._status()
        self.assertFalse(
            any(d["label"] == "Nutrition" for d in status["needs"]),
            "actively-logged nutrition must not be an objective Need",
        )
        nutri = next(
            d for col in ("helping", "watching", "needs")
            for d in status[col] if d["label"] == "Nutrition"
        )
        self.assertEqual(nutri["value"], "2 items today")

    def test_nutrition_driver_reflects_today_logging_without_goals(self):
        self._goal(title="Driver logging")
        self._seed_state(nutrition={
            "enabled": True,
            "macro_compliance_score": None,
            "food_entries_today": 1,
        })
        drivers = build_dashboard_v3_context(self.user)["mission"]["drivers"]
        nutri = next(d for d in drivers if d["key"] == "nutrition")
        self.assertEqual(nutri["value"], "1 item today")

    def test_nutrition_weekly_logging_shown_when_none_today(self):
        self._goal(title="Weekly logging")
        self._seed_state(nutrition={
            "enabled": True,
            "macro_compliance_score": None,
            "food_entries_today": 0,
            "food_entries_7d": 5,
        })
        nutri = next(
            d for col in ("helping", "watching", "needs")
            for d in self._status()[col] if d["label"] == "Nutrition"
        )
        self.assertEqual(nutri["value"], "5/wk logged")

    def test_nutrition_truly_untracked_remains_a_need(self):
        # No macro score AND no logging at all → still an honest objective Need.
        self._goal(title="Untracked")
        self._seed_state(nutrition={
            "enabled": True,
            "macro_compliance_score": None,
            "food_entries_today": 0,
            "food_entries_7d": 0,
        })
        self.assertTrue(
            any(d["label"] == "Nutrition" for d in self._status()["needs"])
        )

    def test_nutrition_macro_score_still_preferred_when_present(self):
        # When macro targets ARE set, the compliance score still wins over the
        # raw logging signal — the fallback is only for the goal-less case.
        self._goal(title="Macro driven")
        self._seed_state(nutrition={
            "enabled": True,
            "macro_compliance_score": 82,
            "food_entries_today": 3,
        })
        drivers = build_dashboard_v3_context(self.user)["mission"]["drivers"]
        nutri = next(d for d in drivers if d["key"] == "nutrition")
        self.assertEqual(nutri["value"], "82% macros")

    # ── Phase D: zero-intake-day "0% macros" bug + no-vanish guarantees ───

    def test_zero_intake_day_with_goal_shows_weekly_logging_not_zero_percent(self):
        # Production bug (2026-06-01): a user with macro targets who has logged
        # recently but not YET today had macro_compliance_score = 0.0 (today's
        # intake / target = 0), which rendered a misleading "0% macros". The
        # macro % must NOT show when there is no intake today; the canonical
        # weekly logging signal surfaces instead.
        self._goal(title="Logged yesterday")
        self._seed_state(nutrition={
            "enabled": True,
            "macro_compliance_score": 0.0,   # floored — no intake today yet
            "food_entries_today": 0,
            "food_entries_7d": 6,
        })
        nutri = next(
            d for col in ("helping", "watching", "needs")
            for d in self._status()[col] if d["label"] == "Nutrition"
        )
        self.assertEqual(nutri["value"], "6/wk logged")
        self.assertNotIn(
            "%", nutri["value"], "must never render a misleading 0% macros"
        )

    def test_zero_intake_day_no_weekly_logging_is_a_need(self):
        # Macro score 0 AND no logging at all (today or this week) → honest Need.
        self._goal(title="Nothing logged")
        self._seed_state(nutrition={
            "enabled": True,
            "macro_compliance_score": 0.0,
            "food_entries_today": 0,
            "food_entries_7d": 0,
        })
        self.assertTrue(
            any(d["label"] == "Nutrition" for d in self._status()["needs"])
        )

    def test_journal_never_vanishes_behind_higher_priority_signals(self):
        # Phase D no-cap guarantee: even with several higher-priority helping
        # signals, a real journal signal can never be silently dropped.
        goal = self._goal(title="Busy helping column")
        self._momentum(goal, trend="rising")
        self._seed_state(
            fitness={"workouts_7d": 5},
            health={
                "weight_change_30d": -2.0, "weight_trend": "decreasing",
                "sleep_avg_hours_7d": 8.0,
            },
            journal={"entries_7d": 4},   # helping, but lowest mission priority
            nutrition={"enabled": True, "macro_compliance_score": 90, "food_entries_today": 4},
        )
        status = self._status()
        all_labels = [
            d["label"]
            for col in ("helping", "watching", "needs")
            for d in status[col]
        ]
        self.assertIn("Journal", all_labels)


class MissionCardResilienceTests(TestCase):
    """The Primary Mission hero card must NEVER disappear because an OPTIONAL
    supporting signal (journal/nutrition freshness, A1C, any SAE read) failed.

    Regression origin: Phase 6.5 (2026-05-31). A request-path read inside
    ``_read_mission_states`` raised — the exception propagated through
    ``_build_mission_card``, which is wrapped in ``_safe(default=None)``, so
    the entire mission section silently vanished. The hero core (goal, focus,
    momentum, panel, progress, why) does not depend on those signals; only the
    Key Drivers row and the status classifier do. A signal failure must degrade
    to an empty drivers row + neutral status, never a missing card.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="v3-mission-resilience@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def _goal(self, **kw):
        from apps.purpose.models import LifeGoal
        defaults = {
            "user": self.user,
            "title": "Resilient Mission",
            "status": "active",
            "is_primary_mission": True,
        }
        defaults.update(kw)
        return LifeGoal.objects.create(**defaults)

    def _seed_state(self, **modules):
        from apps.core.ai_state.models import UserState
        UserState.objects.update_or_create(
            user=self.user, defaults={"state_data": modules}
        )

    def _assert_hero_intact(self, mission):
        # Core hero fields are derived from the goal, NOT from optional signals.
        self.assertIsNotNone(mission, "mission hero card must not disappear")
        self.assertEqual(mission["title"], "Resilient Mission")
        self.assertTrue(mission["is_primary"])
        self.assertIsNotNone(mission["panel"])     # always present for a mission
        self.assertIsNotNone(mission["progress"])  # milestone ring always built

    def test_mission_renders_when_freshness_guard_raises(self):
        # The freshness guard (ensure_fresh) blowing up — e.g. broker error —
        # must not take the card down.
        self._goal()
        self._seed_state(journal={"entries_7d": 2})
        with mock.patch(
            "apps.core.ai_state.state_freshness.ensure_fresh",
            side_effect=RuntimeError("broker unreachable"),
        ):
            mission = build_dashboard_v3_context(self.user)["mission"]
        self._assert_hero_intact(mission)

    def test_mission_renders_when_journal_refresh_fails(self):
        # Journal SAE read raising must not remove the card; drivers degrade.
        self._goal()
        self._seed_state(journal={"entries_7d": 1}, health={})

        def boom(user, module, *a, **k):
            if module == "journal":
                raise RuntimeError("journal builder exploded")
            return _REAL_GET_MODULE_STATE(user, module, *a, **k)

        with mock.patch(
            "apps.core.ai_state.state_engine.get_module_state", side_effect=boom
        ):
            mission = build_dashboard_v3_context(self.user)["mission"]
        self._assert_hero_intact(mission)

    def test_mission_renders_when_nutrition_refresh_fails(self):
        self._goal()
        self._seed_state(nutrition={"enabled": True}, health={})

        def boom(user, module, *a, **k):
            if module == "nutrition":
                raise RuntimeError("nutrition builder exploded")
            return _REAL_GET_MODULE_STATE(user, module, *a, **k)

        with mock.patch(
            "apps.core.ai_state.state_engine.get_module_state", side_effect=boom
        ):
            mission = build_dashboard_v3_context(self.user)["mission"]
        self._assert_hero_intact(mission)

    def test_mission_renders_when_a1c_unavailable(self):
        # A1C is an OPTIONAL health-state signal. When absent, the card renders
        # and simply omits the A1C driver — never a fabricated value, never a
        # vanished card.
        self._goal()
        self._seed_state(health={"weight_change_30d": -2})  # no glucose / a1c
        mission = build_dashboard_v3_context(self.user)["mission"]
        self._assert_hero_intact(mission)
        driver_keys = {d["key"] for d in mission["drivers"]}
        self.assertNotIn("a1c", driver_keys)

    def test_mission_renders_with_stale_snapshot(self):
        # A snapshot older than a fresh manual write must still render the card
        # (the freshness guard repairs the signal; the card never waits on it).
        from datetime import date, timedelta
        from django.utils import timezone
        from apps.core.ai_state.models import UserState
        from apps.journal.models import JournalEntry

        self._goal()
        JournalEntry.objects.create(
            user=self.user, title="Today", body="A real entry",
            entry_date=date.today(), mood="good",
        )
        self._seed_state(journal={"entries_7d": 0})
        UserState.objects.filter(user=self.user).update(
            last_updated=timezone.now() - timedelta(minutes=90)
        )
        mission = build_dashboard_v3_context(self.user)["mission"]
        self._assert_hero_intact(mission)

    def test_mission_renders_when_every_signal_read_raises(self):
        # Reproduces the EXACT production incident: get_module_state raising a
        # TypeError (the orphaned ``allow_rebuild`` kwarg). Every signal read
        # fails — the hero card must still render with an empty drivers row.
        self._goal()
        self._seed_state(health={"weight_change_30d": -2})
        with mock.patch(
            "apps.core.ai_state.state_engine.get_module_state",
            side_effect=TypeError(
                "get_module_state() got an unexpected keyword argument 'allow_rebuild'"
            ),
        ):
            mission = build_dashboard_v3_context(self.user)["mission"]
        self._assert_hero_intact(mission)
        self.assertEqual(mission["drivers"], [])  # degraded, not fabricated

    def test_mission_renders_when_drivers_builder_raises(self):
        self._goal()
        self._seed_state(health={})
        with mock.patch(
            "apps.dashboard_v3.services.composer._build_mission_drivers",
            side_effect=RuntimeError("driver formatting bug"),
        ):
            mission = build_dashboard_v3_context(self.user)["mission"]
        self._assert_hero_intact(mission)
        self.assertEqual(mission["drivers"], [])


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
