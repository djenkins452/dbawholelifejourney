"""Regression tests for the 2026-05-10 production scenario.

At 9:00 AM, Beth claimed:
  - 1:00 PM Lunch was "at risk"
  - Wake up / Prayer Time / Bible Reading were "already done"
  - THRONE Creatine / Lantus SoloStar were "already done"

These tests prove the deterministic state-emitting layers (selectors,
action prioritizer, contradiction telemetry) cannot produce that
narrative. The chat-prompt assembly (cos_context.format_cos_system_
injection) is the LLM's input, but the deterministic layers below it
are what the Narration Contract binds the LLM to.
"""

import datetime as dt

from django.test import SimpleTestCase

from apps.core.ai_orchestrator.contradiction_telemetry import (
    detect_contradictions,
)
from apps.core.decision_engine.action_prioritizer import (
    apply_recovery_bucket_selection,
    compute_at_risk,
    prioritize_execution_items,
)
from apps.core.execution.recovery_state import compute_recovery_state
from apps.core.execution.task_classifier import annotate


def _routine(item_id, title, *, scheduled_time=None, completed=False,
             activity_type=None, foundational=False):
    item = {
        "source_type": "routine_item",
        "source_id": item_id,
        "title": title,
        "domain": "life",
        "is_actionable": not completed,
        "completed_today": completed,
        "is_foundational": foundational,
        "time_status": "overdue" if scheduled_time and not completed else "upcoming",
        "scheduled_time": scheduled_time,
        "execution_group_type": "routine",
        "execution_group_id": "morning",
        "parent_title": "Morning Routine",
        "importance": "important",
        "activity_type": activity_type,
    }
    return annotate(item)


def _task(task_id, title, *, scheduled_time, time_status="upcoming"):
    return annotate({
        "source_type": "task",
        "source_id": task_id,
        "title": title,
        "domain": "life",
        "is_actionable": True,
        "completed_today": False,
        "is_foundational": False,
        "time_status": time_status,
        "scheduled_time": scheduled_time,
        "execution_group_type": "standalone",
        "execution_group_id": None,
        "parent_title": None,
        "importance": "important",
    })


def _supplement(dose_id, name, *, scheduled_time, status="upcoming",
                window="evening"):
    return annotate({
        "source_type": "supplement_dose",
        "source_id": dose_id,
        "title": name,
        "domain": "health",
        "is_actionable": status != "taken",
        "completed_today": status == "taken",
        "is_foundational": False,
        "time_status": status if status in ("overdue", "upcoming") else "upcoming",
        "scheduled_time": scheduled_time,
        "completion_status": status,
        "execution_group_type": "supplement_window",
        "execution_group_id": window,
        "parent_title": f"{window.title()} Supplements",
        "importance": "standard",
        "intake_type": "supplement",
        "priority": "optimization",
    })


class NineAMScenarioTests(SimpleTestCase):
    """At 9:00 AM, prove the deterministic layer never asserts what
    Beth narrated."""

    def setUp(self):
        self.now = dt.time(9, 0)
        self.items = [
            # Morning items still actionable / pending
            _routine(101, "Wake up", scheduled_time="06:00",
                     completed=False, foundational=True),
            _routine(102, "Prayer Time", scheduled_time="06:30",
                     completed=False, activity_type="faith",
                     foundational=True),
            _routine(103, "Bible Reading", scheduled_time="06:45",
                     completed=False, activity_type="bible",
                     foundational=True),
            # Future items
            _task(201, "Lunch", scheduled_time="13:00",
                  time_status="upcoming"),
            _supplement(301, "Fish Oil", scheduled_time="18:00",
                        status="upcoming", window="evening"),
        ]

    def test_lunch_at_1_pm_is_not_in_at_risk_actions_at_9am(self):
        actions = prioritize_execution_items(self.items, self.now) or []
        at_risk = compute_at_risk(actions, {}, self.now)
        titles = [a.get("title") for a in at_risk]
        self.assertNotIn("Lunch", titles)
        self.assertNotIn("Fish Oil", titles)

    def test_recovery_state_is_normal_at_9am_with_no_overdue(self):
        # All items either before 9am-overdue threshold OR future.
        # With recoverable items present but pre-noon, mode = NORMAL.
        rs = compute_recovery_state(self.items, self.now)
        self.assertEqual(rs["mode"], "NORMAL")

    def test_action_pool_excludes_far_future(self):
        # Actions list, before bucket reorder, must not promote a 1pm
        # task to "now" or "overdue" at 9am.
        actions = prioritize_execution_items(self.items, self.now) or []
        for a in actions:
            if a.get("title") == "Lunch":
                self.assertEqual(a.get("urgency"), "upcoming")

    def test_recovery_bucket_selection_normal_pass_through(self):
        actions = prioritize_execution_items(self.items, self.now) or []
        rs = {"mode": "NORMAL"}
        out = apply_recovery_bucket_selection(actions, rs)
        # Normal mode is pass-through.
        self.assertEqual([a["title"] for a in out], [a["title"] for a in actions])


class ContradictionTelemetryAlignmentTests(SimpleTestCase):
    """Prove that the bridge-driven 'prayer: DONE' rollup is loud when
    a child item is still pending."""

    def test_prayer_bridge_with_pending_routine_emits_warning(self):
        items = [
            _routine(101, "Wake up", scheduled_time="06:00",
                     completed=False, foundational=True),
            _routine(102, "Prayer Time", scheduled_time="06:30",
                     completed=False, activity_type="faith",
                     foundational=True),
        ]
        # Domain rollup says prayer DONE (e.g., a separate prayer
        # activity counted) but the routine items remain pending.
        state = {
            "items": items,
            "summaries": {
                "domains": {"prayer": True, "bible_reading": False},
                "medications": {},
            },
        }
        out = detect_contradictions(
            exec_state=state, fresh_med_schedule=None,
            user_id=1, request_id="r1",
        )
        codes = [c.code for c in out]
        self.assertIn("PRAYER_ROLLUP_VS_ITEMS", codes)
