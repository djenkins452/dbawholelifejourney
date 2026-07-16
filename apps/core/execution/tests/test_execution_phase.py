"""Day-execution-phase truth tests.

`compute_execution_phase` is the deterministic FACT every surface consumes for
"where is the user in today's execution?" — before their first commitment, underway,
behind, ahead, winding down, or done. It exists so no surface (dashboard / CoS /
notifications / voice) ever re-decides whether the day has begun, and so the Executive
Briefing can never fabricate a "slow start" before the day has begun (incident 2026-07-16).

These are pure-function tests: the phase is derived from provided buckets + a concrete
`now` datetime (so the canonical daypart clock resolves without touching the user).
"""

from datetime import datetime

from django.test import SimpleTestCase

from apps.core.execution.execution_state import compute_execution_phase


def _item(title, sched, *, completed=False, actionable=True, status="pending"):
    return {
        "title": title,
        "scheduled_time": sched,
        "is_actionable": actionable,
        "completed_today": completed,
        "completion_status": status,
    }


def _phase(now, *, items=None, overdue=0, now_actions=0, completed=0,
           next_actions=1, upcoming=0):
    """Run compute_execution_phase with synthetic buckets. Bucket COUNTS are what the
    derivation reads; `items` feeds the timing scans (first commitment / ahead)."""
    def _n(n):
        return [{"title": f"x{i}"} for i in range(n)]
    return compute_execution_phase(
        None, now,
        items=items or [],
        overdue_actions=_n(overdue),
        now_actions=_n(now_actions),
        completed_today=_n(completed),
        next_actions=_n(next_actions),
        upcoming_actions=_n(upcoming),
    )


class BeforeFirstCommitmentTests(SimpleTestCase):
    def test_456am_before_first_commitment(self):
        """The reported case: 4:56 AM, nothing done, first commitment (Prayer Time)
        still in the future → the day has not begun."""
        now = datetime(2026, 7, 16, 4, 56)
        items = [_item("Prayer Time", "5:30 AM"),
                 _item("Bible reading", "5:45 AM")]
        pf = _phase(now, items=items, next_actions=2)
        self.assertEqual(pf["phase"], "before_first_commitment")
        self.assertTrue(pf["before_first_commitment"])
        self.assertFalse(pf["day_begun"])
        self.assertEqual(pf["first_commitment"]["title"], "Prayer Time")
        self.assertEqual(pf["minutes_until_first_commitment"], 34)

    def test_clean_slate_no_commitments(self):
        now = datetime(2026, 7, 16, 6, 0)
        pf = _phase(now, items=[], next_actions=0)
        self.assertEqual(pf["phase"], "before_first_commitment")
        self.assertIsNone(pf["first_commitment"])


class BehindTests(SimpleTestCase):
    def test_overdue_makes_behind(self):
        now = datetime(2026, 7, 16, 10, 0)
        pf = _phase(now, overdue=2, next_actions=1)
        self.assertEqual(pf["phase"], "behind")
        self.assertTrue(pf["behind"])
        self.assertEqual(pf["overdue_count"], 2)

    def test_behind_outranks_clock(self):
        """Overdue at any hour reads as behind — execution truth beats the clock."""
        now = datetime(2026, 7, 16, 15, 30)
        pf = _phase(now, overdue=1)
        self.assertEqual(pf["phase"], "behind")


class AheadTests(SimpleTestCase):
    def test_future_work_done_early_is_ahead(self):
        now = datetime(2026, 7, 16, 8, 0)
        # A 10:00 AM commitment already completed at 8:00 AM → ahead.
        items = [_item("Workout", "10:00 AM", completed=True, status="completed")]
        pf = _phase(now, items=items, completed=1, next_actions=1)
        self.assertEqual(pf["phase"], "ahead")
        self.assertTrue(pf["ahead"])


class OnTrackClockFramingTests(SimpleTestCase):
    def test_begun_morning_is_underway(self):
        now = datetime(2026, 7, 16, 7, 0)
        # Completed a 6:00 item (not ahead), nothing overdue → underway.
        items = [_item("Meds", "6:00 AM", completed=True, status="completed")]
        pf = _phase(now, items=items, completed=1, next_actions=1)
        self.assertEqual(pf["phase"], "underway")

    def test_begun_midday(self):
        now = datetime(2026, 7, 16, 12, 30)
        items = [_item("Meds", "6:00 AM", completed=True, status="completed")]
        pf = _phase(now, items=items, completed=1, next_actions=1)
        self.assertEqual(pf["phase"], "midday")

    def test_begun_afternoon(self):
        now = datetime(2026, 7, 16, 15, 0)
        items = [_item("Meds", "6:00 AM", completed=True, status="completed")]
        pf = _phase(now, items=items, completed=1, next_actions=1)
        self.assertEqual(pf["phase"], "afternoon")

    def test_begun_evening_winding_down(self):
        now = datetime(2026, 7, 16, 18, 0)
        items = [_item("Meds", "6:00 AM", completed=True, status="completed")]
        pf = _phase(now, items=items, completed=1, next_actions=1)
        self.assertEqual(pf["phase"], "winding_down")


class DayCompleteTests(SimpleTestCase):
    def test_nothing_remaining_after_begun_is_complete(self):
        now = datetime(2026, 7, 16, 20, 0)
        pf = _phase(now, completed=3, next_actions=0, upcoming=0)
        self.assertEqual(pf["phase"], "day_complete")
        self.assertTrue(pf["day_complete"])


class FactsContractTests(SimpleTestCase):
    def test_facts_only_no_verdict_keys(self):
        """The phase dict is FACTS only — no coaching/verdict strings leak in."""
        pf = _phase(datetime(2026, 7, 16, 10, 0), overdue=1)
        for key in ("phase", "day_begun", "before_first_commitment", "behind",
                    "ahead", "completed_count", "overdue_count", "remaining_count",
                    "clock_phase", "hour"):
            self.assertIn(key, pf)
        # No free-text narrative fields — the narrator authors those.
        self.assertNotIn("headline", pf)
        self.assertNotIn("message", pf)

    def test_never_raises_returns_unknown_on_bad_input(self):
        # items=None-ish / malformed still yields a neutral, non-fabricating phase.
        pf = compute_execution_phase(
            None, "not-a-datetime", items=None, overdue_actions=None,
            now_actions=None, completed_today=None, next_actions=None,
            upcoming_actions=None,
        )
        self.assertIn(pf["phase"], ("unknown", "before_first_commitment",
                                    "day_complete", "underway", "midday",
                                    "afternoon", "winding_down"))
