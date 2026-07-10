"""Execution timing = deterministic CALCULATIONS only (facts, never judgments).

Proves WLJ hands the model computed results (minutes late, buffer, earliest completion,
latest safe start, fits-before-anchor, required pace) so the model never does date
arithmetic — and that WLJ emits NO judgment vocabulary (that is the model's job)."""
import json

from django.test import SimpleTestCase
from django.utils import timezone

from apps.core.execution.timing import compute_execution_timing, estimate_duration


def _item(title, sched_hhmm, *, overdue=False, source_type="routine_item"):
    return {
        "title": title,
        "scheduled_time": sched_hhmm,          # "HH:MM" 24h, as build_today_execution emits
        "is_actionable": True,
        "completed_today": False,
        "completion_status": "pending",
        "time_status": "overdue" if overdue else "upcoming",
        "source_type": source_type,
    }


class ExecutionTimingCalculationTests(SimpleTestCase):
    def setUp(self):
        # 6:18 AM. Workout (45m) was due 6:15; supplements after; Shower anchor at 7:00.
        self.now = timezone.now().replace(hour=6, minute=18, second=0, microsecond=0)
        self.state = {"items": [
            _item("Workout", "06:15", overdue=True),
            _item("Protein Shake", "06:20"),
            _item("THORNE Creatine", "06:22"),
            _item("Shower", "07:00"),
        ]}

    def test_facts_are_calculated_correctly(self):
        t = compute_execution_timing(self.state, self.now)

        self.assertEqual(t["now"], "6:18 AM")
        self.assertEqual(t["next_anchor"]["title"], "Shower")
        self.assertEqual(t["next_anchor"]["minutes_until"], 42)
        self.assertEqual(t["buffer_minutes"], 42)

        workout = next(r for r in t["remaining"] if r["title"] == "Workout")
        self.assertEqual(workout["minutes_late"], 3)              # 6:18 − 6:15
        self.assertEqual(workout["duration_estimate_min"], 45)
        self.assertEqual(workout["earliest_completion"], "7:03 AM")  # 6:18 + 45
        self.assertEqual(workout["latest_safe_start"], "6:15 AM")     # 7:00 − 45
        self.assertFalse(workout["fits_before_next_anchor"])         # 7:03 > 7:00

        # Required pace: 45+3+2 = 50 min of work, 42 min window → −8 slack (over-committed).
        self.assertEqual(t["required_pace"]["work_min"], 50)
        self.assertEqual(t["required_pace"]["window_min"], 42)
        self.assertEqual(t["required_pace"]["slack_min"], -8)

        # The anchor is the deadline, not "remaining work" to fit before it.
        self.assertNotIn("Shower", [r["title"] for r in t["remaining"]])

    def test_no_judgment_vocabulary_in_the_facts(self):
        """WLJ emits numbers/times/booleans only. 'behind', 'risk', 'recover', 'act now'
        are the model's conclusions — they must never appear in the deterministic facts."""
        blob = json.dumps(compute_execution_timing(self.state, self.now)).lower()
        for judgment in ("behind", "at risk", "serious risk", "recover", "act now",
                         "slipping", "on track", "urgent", "critical"):
            self.assertNotIn(judgment, blob)

    def test_no_anchor_means_no_deadline_pressure(self):
        state = {"items": [_item("Workout", "06:15", overdue=True)]}
        t = compute_execution_timing(state, self.now)
        self.assertIsNone(t["next_anchor"])
        self.assertIsNone(t["buffer_minutes"])
        self.assertIsNone(t["required_pace"])
        # No deadline → fits is True (nothing to miss).
        self.assertTrue(t["remaining"][0]["fits_before_next_anchor"])
        self.assertIsNone(t["remaining"][0]["latest_safe_start"])

    def test_estimate_duration_is_deterministic(self):
        self.assertEqual(estimate_duration("Workout"), 45)
        self.assertEqual(estimate_duration("THORNE Creatine"), 2)
        self.assertEqual(estimate_duration("Something Unknown"), 5)  # fallback
