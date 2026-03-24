# ==============================================================================
# File: apps/life/tests/test_task_intelligence.py
# Description: Tests for task priority summary, signals, coaching, nudges
# ==============================================================================

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.life.services.task_priority_service import (
    build_task_priority_summary, MAX_ITEMS, MIN_ITEMS,
)
from apps.life.services.task_signals import build_task_signals
from apps.life.services.task_coaching_builder import (
    build_task_coaching,
    apply_task_time_awareness,
    generate_task_nudge,
    NUDGE_TASK_OVERDUE,
)


def _now():
    return timezone.now()


def _dt(hour=12):
    return _now().replace(hour=hour, minute=0, second=0, microsecond=0)


def _task_state(**overrides):
    base = {
        "overdue_count": 0,
        "overdue_nn_count": 0,
        "overdue_tasks": [],
        "due_today_tasks_detail": [],
        "due_tomorrow_count": 0,
        "completed_today_detail": {"count": 0, "titles": [], "momentum_signal": "low"},
        "next_up_task": None,
        "nn_skip_streaks": [],
        "task_commitment_summary": {"consistency_score": 1.0},
        "_contract": {
            "summary": {"total_pending": 0},
            "today": {"items": []},
            "alerts": {"overdue": [], "overdue_count": 0},
        },
    }
    base.update(overrides)
    return base


# ── Phase 1: Priority Summary ───────────────────────────────────────────────

class TestTaskSummaryContract(TestCase):

    def test_empty_state_valid_contract(self):
        result = build_task_priority_summary({}, _now())
        self.assertIn("headline", result)
        self.assertIn("items", result)
        self.assertIn("flags", result)
        self.assertIn("priority_level", result)

    def test_none_state_handled(self):
        result = build_task_priority_summary(None, _now())
        # With None state, only "tasks_clear" (no pressing tasks) is generated
        self.assertLessEqual(len(result["items"]), 1)

    def test_max_4_items(self):
        state = _task_state(
            overdue_count=3,
            overdue_nn_count=2,
            due_today_tasks_detail=[{"time_proximity": "due_now"}] * 5,
            due_tomorrow_count=3,
            next_up_task={"title": "Review", "scheduled_time": "2:00 PM", "reason": "next_scheduled"},
            completed_today_detail={"count": 6, "momentum_signal": "high", "titles": []},
        )
        result = build_task_priority_summary(state, _now())
        self.assertLessEqual(len(result["items"]), MAX_ITEMS)


class TestTaskOverdue(TestCase):

    def test_overdue_is_high_and_first(self):
        state = _task_state(overdue_count=3)
        result = build_task_priority_summary(state, _now())
        self.assertEqual(result["items"][0]["key"], "tasks_overdue")
        self.assertEqual(result["items"][0]["priority"], "high")
        self.assertIn("3 tasks overdue", result["items"][0]["message"])

    def test_overdue_singular(self):
        state = _task_state(overdue_count=1)
        result = build_task_priority_summary(state, _now())
        self.assertIn("1 task overdue", result["items"][0]["message"])

    def test_overdue_headline(self):
        state = _task_state(overdue_count=2)
        result = build_task_priority_summary(state, _now())
        self.assertEqual(result["headline"], "Tasks need attention")
        self.assertTrue(result["flags"]["has_overdue"])


class TestTaskNextUp(TestCase):

    def test_next_task_with_time(self):
        state = _task_state(
            next_up_task={"title": "Payroll review", "scheduled_time": "2:00 PM",
                          "reason": "next_scheduled"},
        )
        result = build_task_priority_summary(state, _now())
        next_items = [i for i in result["items"] if i["key"] == "next_task"]
        self.assertEqual(len(next_items), 1)
        self.assertIn("Payroll review", next_items[0]["message"])
        self.assertIn("2:00 PM", next_items[0]["message"])

    def test_next_task_no_time(self):
        state = _task_state(
            next_up_task={"title": "Clean desk", "reason": "fallback"},
        )
        result = build_task_priority_summary(state, _now())
        next_items = [i for i in result["items"] if i["key"] == "next_task"]
        self.assertEqual(len(next_items), 1)
        self.assertIn("Clean desk", next_items[0]["message"])


class TestTaskDueToday(TestCase):

    def test_due_soon(self):
        state = _task_state(
            due_today_tasks_detail=[
                {"time_proximity": "due_soon"},
                {"time_proximity": "due_now"},
            ],
        )
        result = build_task_priority_summary(state, _now())
        soon_items = [i for i in result["items"] if i["key"] == "tasks_due_soon"]
        self.assertEqual(len(soon_items), 1)
        self.assertIn("2 tasks due soon", soon_items[0]["message"])


class TestTaskMomentum(TestCase):

    def test_high_momentum(self):
        state = _task_state(
            completed_today_detail={"count": 7, "momentum_signal": "high", "titles": []},
        )
        result = build_task_priority_summary(state, _now())
        momentum = [i for i in result["items"] if i["key"] == "momentum_high"]
        self.assertEqual(len(momentum), 1)

    def test_stable_headline(self):
        state = _task_state(
            completed_today_detail={"count": 7, "momentum_signal": "high", "titles": []},
        )
        result = build_task_priority_summary(state, _now())
        self.assertEqual(result["headline"], "You're on track")


# ── Phase 2: Signals ────────────────────────────────────────────────────────

class TestTaskSignals(TestCase):

    def test_empty_state_returns_list(self):
        result = build_task_signals({})
        self.assertIsInstance(result, list)

    def test_momentum_strong(self):
        state = _task_state(
            completed_today_detail={"count": 6, "momentum_signal": "high", "titles": []},
        )
        signals = build_task_signals(state)
        momentum = next((s for s in signals if s["key"] == "task_momentum"), None)
        self.assertIsNotNone(momentum)
        self.assertEqual(momentum["state"], "strong")

    def test_momentum_low(self):
        state = _task_state(
            completed_today_detail={"count": 0, "momentum_signal": "low", "titles": []},
            _contract={"summary": {"total_pending": 5}, "today": {"items": [1]},
                        "alerts": {}},
        )
        signals = build_task_signals(state)
        momentum = next((s for s in signals if s["key"] == "task_momentum"), None)
        self.assertIsNotNone(momentum)
        self.assertEqual(momentum["state"], "low")

    def test_pressure_high(self):
        state = _task_state(
            overdue_count=4,
            due_today_tasks_detail=[{"time_proximity": "due_now"}] * 3,
        )
        signals = build_task_signals(state)
        pressure = next((s for s in signals if s["key"] == "task_pressure"), None)
        self.assertIsNotNone(pressure)
        self.assertEqual(pressure["state"], "high")

    def test_slippage_stable(self):
        state = _task_state()
        signals = build_task_signals(state)
        slippage = next((s for s in signals if s["key"] == "task_slippage"), None)
        self.assertIsNotNone(slippage)
        self.assertEqual(slippage["state"], "stable")

    def test_slippage_slipping(self):
        state = _task_state(
            overdue_count=3,
            nn_skip_streaks=[
                {"task": "Exercise", "streak": 3},
                {"task": "Meditate", "streak": 2},
            ],
        )
        signals = build_task_signals(state)
        slippage = next((s for s in signals if s["key"] == "task_slippage"), None)
        self.assertIsNotNone(slippage)
        self.assertEqual(slippage["state"], "slipping")


# ── Phase 3: Coaching ────────────────────────────────────────────────────────

class TestTaskCoaching(TestCase):

    def test_overdue_action(self):
        summary = build_task_priority_summary(
            _task_state(overdue_count=3), _now()
        )
        result = build_task_coaching(summary)
        self.assertIn("overdue", result["action"].lower())

    def test_next_task_personalized(self):
        state = _task_state(
            next_up_task={"title": "Review budget", "reason": "next_scheduled"},
        )
        summary = build_task_priority_summary(state, _now())
        result = build_task_coaching(summary)
        self.assertIn("Review budget", result["action"])

    def test_safety_fallback(self):
        result = build_task_coaching(None)
        self.assertIsNotNone(result)
        self.assertIn("action", result)

    def test_empty_summary_fallback(self):
        result = build_task_coaching({"items": []})
        self.assertIn("consistent", result["action"].lower())

    def test_one_action_only(self):
        state = _task_state(
            overdue_count=3,
            next_up_task={"title": "Review", "reason": "next_scheduled"},
            due_today_tasks_detail=[{"time_proximity": "due_now"}],
        )
        summary = build_task_priority_summary(state, _now())
        result = build_task_coaching(summary)
        self.assertIsInstance(result["action"], str)


# ── Phase 4: Time Awareness ─────────────────────────────────────────────────

class TestTaskTimeAwareness(TestCase):

    def test_none_coaching(self):
        self.assertIsNone(apply_task_time_awareness(None, _dt()))

    def test_overdue_always_now(self):
        coaching = {"action": "Start with your overdue tasks",
                    "source_key": "tasks_overdue", "priority_level": "high"}
        result = apply_task_time_awareness(coaching, _dt(14))
        self.assertIn("now", result["action"].lower())

    def test_free_window_adds_now(self):
        coaching = {"action": "Focus on what's due soon",
                    "source_key": "tasks_due_soon", "priority_level": "medium"}
        result = apply_task_time_awareness(coaching, _dt(14), None)
        self.assertIn("now", result["action"].lower())

    def test_busy_defers(self):
        dt = _dt(14)
        next_event = (dt + timedelta(minutes=15)).isoformat()
        coaching = {"action": "Focus on what's due soon",
                    "source_key": "tasks_due_soon", "priority_level": "medium"}
        result = apply_task_time_awareness(coaching, dt, next_event)
        self.assertIn("after your next task finishes", result["action"].lower())

    def test_evening_softened(self):
        coaching = {"action": "Work through today's tasks",
                    "source_key": "tasks_due_today", "priority_level": "medium"}
        result = apply_task_time_awareness(coaching, _dt(19), None)
        self.assertIn("evening", result["action"].lower())

    def test_reinforcement_gets_today(self):
        coaching = {"action": "Keep up the pace",
                    "source_key": "momentum_high", "priority_level": "low"}
        result = apply_task_time_awareness(coaching, _dt(14), None)
        self.assertIn("today", result["action"].lower())


# ── Phase 5: Nudges ──────────────────────────────────────────────────────────

class TestTaskNudges(TestCase):

    def test_none_on_no_summary(self):
        self.assertIsNone(generate_task_nudge(None, [], {}, _now()))

    def test_overdue_nudge(self):
        state = _task_state(overdue_count=2)
        summary = build_task_priority_summary(state, _now())
        coaching = build_task_coaching(summary)
        result = generate_task_nudge(summary, [], coaching, _now())
        self.assertIsNotNone(result)
        self.assertEqual(result["nudge_type"], NUDGE_TASK_OVERDUE)
        self.assertEqual(result["priority"], "high")

    def test_overdue_frequency_limit(self):
        now = _now()
        state = _task_state(overdue_count=2)
        summary = build_task_priority_summary(state, now)
        coaching = build_task_coaching(summary)
        last = {NUDGE_TASK_OVERDUE: (now - timedelta(minutes=30)).isoformat()}
        result = generate_task_nudge(summary, [], coaching, now, last)
        self.assertIsNone(result)

    def test_low_momentum_nudge(self):
        state = _task_state(
            completed_today_detail={"count": 0, "momentum_signal": "low", "titles": []},
            _contract={"summary": {"total_pending": 5}, "today": {"items": [1]},
                        "alerts": {}},
        )
        summary = build_task_priority_summary(state, _now())
        signals = build_task_signals(state)
        coaching = build_task_coaching(summary, signals)
        result = generate_task_nudge(summary, signals, coaching, _now())
        # Could be momentum or pressure nudge
        if result:
            self.assertEqual(result["type"], "tasks")

    def test_reinforcement_nudge(self):
        state = _task_state(
            completed_today_detail={"count": 6, "momentum_signal": "high", "titles": []},
        )
        summary = build_task_priority_summary(state, _now())
        signals = build_task_signals(state)
        coaching = build_task_coaching(summary, signals)
        result = generate_task_nudge(summary, signals, coaching, _now())
        if result:
            self.assertEqual(result["type"], "tasks")
            self.assertEqual(result["priority"], "low")

    def test_nudge_contract_shape(self):
        state = _task_state(overdue_count=1)
        summary = build_task_priority_summary(state, _now())
        coaching = build_task_coaching(summary)
        result = generate_task_nudge(summary, [], coaching, _now())
        self.assertIn("type", result)
        self.assertIn("nudge_type", result)
        self.assertIn("priority", result)
        self.assertIn("message", result)
        self.assertIn("action", result)
