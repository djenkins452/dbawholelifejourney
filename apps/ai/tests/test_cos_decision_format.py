"""
Phase 19 — CoS Decision-Layer Format tests.

Covers the 4-part CoS response structure emitted by the deterministic
decision handlers (focus / biggest-risk / fix-first):

    (1) Quick wins      — optional, max 2
    (2) Primary action  — required unless intentional shutdown
    (3) Context         — optional signal-based reason
    (4) Stop condition  — late-evening shutdown wording

Seven scenarios from the Phase 19 brief:

    1. quick + primary (day)
    2. quick + shutdown (night)
    3. primary only (day)
    4. primary only (night)
    5. risk-driven response
    6. no quick wins available
    7. deduplication (quick overlaps primary)
"""

from datetime import date, datetime
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from apps.ai.deterministic_router import (
    _build_focus_query_response,
    _format_cos_decision_response,
    _is_late_evening,
)
from apps.ai.tests._cos_decision_helpers import assert_cos_action_first
from apps.users.models import User


# ── Test helpers ────────────────────────────────────────────────────

def _make_user(email):
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(
        email=email, password="testpass123",
        date_of_birth=date(1990, 1, 1),
    )
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _fake_execution(items):
    def builder(user):
        return {'items': items, 'summaries': {}}
    return builder


def _med(title, scheduled_time='07:00', importance='foundational',
         completed=False, time_status='overdue', id_=None):
    return {
        'id': id_ or hash(title) % 10000,
        'source_type': 'medication_dose',
        'source_id': hash(title) % 10000,
        'title': title,
        'domain': 'health',
        'importance': importance,
        'time_status': time_status,
        'scheduled_time': scheduled_time,
        'completed_today': completed,
        'is_actionable': True,
        'is_foundational': importance == 'foundational',
        'execution_group_type': 'medication_window',
        'execution_group_id': 'morning',
        'parent_title': 'Morning Medications',
    }


def _task(title, scheduled_time='05:15', time_status='overdue',
          completed=False, id_=None):
    return {
        'id': id_ or hash(title) % 10000,
        'source_type': 'task',
        'source_id': hash(title) % 10000,
        'title': title,
        'domain': 'life',
        'importance': 'foundational',
        'time_status': time_status,
        'scheduled_time': scheduled_time,
        'completed_today': completed,
        'is_actionable': True,
        'is_foundational': True,
        'execution_group_type': 'standalone',
        'execution_group_id': None,
        'parent_title': None,
    }


# ═══════════════════════════════════════════════════════════════════
# 1. Formatter unit tests (SimpleTestCase — no DB)
# ═══════════════════════════════════════════════════════════════════

class CosDecisionFormatterTests(SimpleTestCase):
    """The four-part formatter in isolation."""

    def test_quick_plus_primary_day(self):
        out = _format_cos_decision_response(
            quick_wins=["your Magnesium", "your Metformin"],
            primary_action="start your next task block and clear your top priority",
        )
        self.assertIn("Take your Magnesium and your Metformin now", out)
        self.assertIn("both are quick and overdue", out)
        self.assertIn("Then start your next task block", out)
        self.assertTrue(out.endswith("."))

    def test_quick_plus_shutdown_night(self):
        out = _format_cos_decision_response(
            quick_wins=["your Magnesium", "your Metformin"],
            primary_action="shut it down for the night so tomorrow starts clean",
        )
        self.assertIn("Take your Magnesium and your Metformin now", out)
        self.assertIn("Then shut it down for the night", out)

    def test_primary_only_day(self):
        out = _format_cos_decision_response(
            primary_action="Start Workout",
            context_reason="Workout (scheduled at 06:15) is overdue",
        )
        lines = out.splitlines()
        self.assertEqual(lines[0], "Start Workout.")
        self.assertIn("Workout (scheduled at 06:15) is overdue", lines[1])

    def test_primary_only_night(self):
        out = _format_cos_decision_response(
            primary_action="shut it down for the night",
        )
        # Standalone primary is sentence-cased.
        self.assertEqual(out, "Shut it down for the night.")

    def test_risk_lead_with_context(self):
        out = _format_cos_decision_response(
            primary_action="Get a 20-minute walk in now — that's your highest-impact move",
            context_reason="Your glucose is trending up and your workout streak broke",
            lead_with_context=True,
        )
        lines = out.splitlines()
        self.assertIn("glucose is trending up", lines[0])
        self.assertIn("Then get a 20-minute walk", lines[1])

    def test_quick_wins_capped_at_two(self):
        out = _format_cos_decision_response(
            quick_wins=["A", "B", "C", "D"],
            primary_action="Start Workout",
        )
        # Only A and B should appear in the quick-wins line.
        self.assertIn("A", out)
        self.assertIn("B", out)
        self.assertNotIn("C", out)
        self.assertNotIn("D", out)

    def test_single_quick_win_phrasing(self):
        out = _format_cos_decision_response(
            quick_wins=["your Magnesium"],
            primary_action="Start Workout",
        )
        # Singular phrasing drops "both".
        self.assertIn("Take your Magnesium now — quick and overdue.", out)
        self.assertNotIn("both are quick", out)

    def test_empty_inputs_produce_empty_string(self):
        out = _format_cos_decision_response()
        self.assertEqual(out, "")

    def test_no_legacy_markers_in_output(self):
        out = _format_cos_decision_response(
            quick_wins=["your Magnesium"],
            primary_action="Start Workout",
            context_reason="It's overdue",
        )
        # Phase 19: old markers are gone.
        self.assertNotIn("Do this next:", out)
        self.assertNotIn("Reason:", out)
        self.assertNotIn("Priority:", out)


# ═══════════════════════════════════════════════════════════════════
# 2. _is_late_evening helper
# ═══════════════════════════════════════════════════════════════════

class IsLateEveningTests(SimpleTestCase):
    def test_returns_bool_on_missing_timezone(self):
        class _FakeUser:
            id = 1
        # No preferences/timezone — helper must fail-safe to False.
        self.assertFalse(_is_late_evening(_FakeUser()))

    def test_late_at_22(self):
        from unittest.mock import MagicMock
        fake_now = datetime(2026, 4, 22, 22, 30)
        with patch(
            "apps.core.utils.get_user_now", return_value=fake_now,
        ):
            self.assertTrue(_is_late_evening(MagicMock()))

    def test_not_late_at_14(self):
        from unittest.mock import MagicMock
        fake_now = datetime(2026, 4, 22, 14, 0)
        with patch(
            "apps.core.utils.get_user_now", return_value=fake_now,
        ):
            self.assertFalse(_is_late_evening(MagicMock()))

    def test_early_morning_is_late(self):
        from unittest.mock import MagicMock
        # 3am is still "late night" in our contract.
        fake_now = datetime(2026, 4, 22, 3, 0)
        with patch(
            "apps.core.utils.get_user_now", return_value=fake_now,
        ):
            self.assertTrue(_is_late_evening(MagicMock()))


# ═══════════════════════════════════════════════════════════════════
# 3. Integration — the 7 brief scenarios against _build_focus_query_response
# ═══════════════════════════════════════════════════════════════════

class Phase19FocusScenarioTests(TestCase):
    def setUp(self):
        self.user = _make_user("phase19_focus@test.com")

    def _run(self, items, *, late=False):
        from apps.core.ai_state import state_builder
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"execution": _fake_execution(items)},
        ), patch(
            "apps.ai.deterministic_router._is_late_evening",
            return_value=late,
        ):
            return _build_focus_query_response(self.user)

    # 1. quick + primary (day)
    def test_scenario_1_quick_plus_primary_day(self):
        items = [
            _med("Magnesium", "07:00", id_=11),
            _med("Metformin", "07:05", id_=12),
            _task("Work on WLJ", "05:15", id_=21),
        ]
        resp = self._run(items, late=False)
        assert_cos_action_first(
            self, resp,
            must_contain=("Magnesium", "Metformin", "Work on WLJ"),
        )
        self.assertIn("Then", resp)

    # 2. quick + shutdown (night)
    def test_scenario_2_quick_plus_shutdown_night(self):
        # Only meds overdue; no tasks → late evening → shutdown primary.
        items = [
            _med("Magnesium", "07:00", id_=11),
            _med("Metformin", "07:05", id_=12),
        ]
        resp = self._run(items, late=True)
        assert_cos_action_first(
            self, resp,
            must_contain=("Magnesium", "Metformin", "shut it down"),
        )

    # 3. primary only (day)
    def test_scenario_3_primary_only_day(self):
        items = [_task("Work on WLJ", "05:15", id_=21)]
        resp = self._run(items, late=False)
        assert_cos_action_first(
            self, resp,
            must_contain=("Work on WLJ", "overdue"),
            must_not_contain=("Then ",),
        )

    # 4. primary only (night)
    def test_scenario_4_primary_only_night(self):
        # A task still surfaces even late — the formatter just doesn't
        # auto-append a shutdown. Brief: "late evening → no heavy new
        # work" is honored by the upstream selector keeping foundational
        # items; the formatter itself never swaps a real primary.
        items = [_task("Journal", "20:00", time_status='overdue', id_=21)]
        resp = self._run(items, late=True)
        assert_cos_action_first(
            self, resp,
            must_contain=("Journal",),
        )

    # 6. no quick wins available (distinct from "primary only day" —
    #    this tests the explicit absence of med/supp overdue items)
    def test_scenario_6_no_quick_wins(self):
        # Only a regular task, no meds/supps at all → no quick-wins line.
        items = [_task("Finish report", "10:00", id_=21)]
        resp = self._run(items, late=False)
        assert_cos_action_first(
            self, resp,
            must_contain=("Finish report",),
            must_not_contain=("quick and overdue", "Then "),
        )

    # 7. deduplication — quick-win item should not also appear as primary
    def test_scenario_7_dedup_quick_overlapping_primary(self):
        # Single overdue med: candidate for both quick-wins AND
        # primary. Formatter must dedupe — primary must be a DIFFERENT
        # recovery item OR the late-evening shutdown.
        items = [_med("Magnesium", "07:00", id_=11)]
        resp = self._run(items, late=True)
        # Quick-wins line contains "your Magnesium" once.
        self.assertEqual(
            resp.count("your Magnesium"), 1,
            f"Magnesium appears more than once: {resp!r}",
        )
        # Primary is the shutdown, not "Start Magnesium" again.
        self.assertNotIn("Start Magnesium", resp)


# ═══════════════════════════════════════════════════════════════════
# 4. Risk-driven scenario (biggest_risk handler leads with context)
# ═══════════════════════════════════════════════════════════════════

class Phase19RiskScenarioTests(TestCase):
    def setUp(self):
        self.user = _make_user("phase19_risk@test.com")

    def test_scenario_5_risk_response_leads_with_context(self):
        from apps.ai.deterministic_router import _build_biggest_risk_response
        from apps.core.ai_orchestrator import cos_context

        def fake_fresh(user, module):
            if module == 'medicine':
                return {
                    'expected_today': 10,
                    'today_taken': 0,
                    'adherence_7d': 55,
                }
            return {}

        with patch.object(cos_context, '_fresh_module_state', fake_fresh):
            resp = _build_biggest_risk_response(self.user)

        assert_cos_action_first(self, resp)
        lines = [ln for ln in resp.splitlines() if ln.strip()]
        self.assertTrue(lines)
        # First line is the risk context (not an imperative).
        first = lines[0]
        self.assertFalse(
            first.startswith("Take "),
            f"risk response should lead with context, got: {first!r}",
        )
        # The primary action ("Then take your overdue medications now")
        # appears on a later line.
        self.assertTrue(any("Then" in ln for ln in lines))
