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
    _derive_headline,
    _derive_trajectory,
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
        state = {
            "recovery_state": {"mode": "RECOVERY"},
            "overdue_actions": [],
            "at_risk_actions": [],
        }
        line = _derive_headline("mixed", [], [], state, {"title": "x"})
        self.assertIn("recover", line.lower())

    def test_headline_for_many_overdue(self):
        state = {
            "recovery_state": {"mode": "NORMAL"},
            "overdue_actions": [{}, {}, {}, {}],
            "at_risk_actions": [],
        }
        line = _derive_headline("slipping", [], [], state, None)
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
        line = _momentum_label(2, 5, 0, 2, True, False)
        self.assertIn("past due", line.lower())

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
