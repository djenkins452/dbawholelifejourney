# ==============================================================================
# File: apps/core/proactive/tests/test_nudge_engine.py
# Description: Tests for deterministic health nudge engine
# ==============================================================================

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.proactive.nudge_engine import (
    generate_health_nudge,
    NUDGE_MED_OVERDUE,
    NUDGE_SIGNAL_DECLINE,
    NUDGE_REINFORCEMENT,
)


def _now():
    return timezone.now()


def _summary(items, priority_level="low", flags=None):
    return {
        "headline": "Test",
        "priority_level": priority_level,
        "items": items,
        "flags": flags or {},
        "generated_at": _now().isoformat(),
    }


def _item(key, priority, message):
    return {"key": key, "priority": priority, "message": message,
            "category": "medical", "icon": "pill"}


def _coaching(action="Stay consistent", reason="Good", source_key="bp_normal"):
    return {"action": action, "reason": reason,
            "priority_level": "low", "source_key": source_key}


class TestNudgeContract(TestCase):
    """Output shape and None handling."""

    def test_returns_none_on_no_summary(self):
        self.assertIsNone(generate_health_nudge(None, [], {}, _now()))

    def test_returns_none_on_no_coaching(self):
        summary = _summary([_item("bp_normal", "low", "BP ok")])
        self.assertIsNone(generate_health_nudge(summary, [], None, _now()))

    def test_nudge_has_required_keys(self):
        summary = _summary(
            [_item("medications_overdue", "high", "2 meds overdue")],
            priority_level="high",
            flags={"has_medication_risk": True, "has_urgent": True},
        )
        coaching = _coaching("Take your medications now", source_key="medications_overdue")
        result = generate_health_nudge(summary, [], coaching, _now())
        self.assertIsNotNone(result)
        self.assertIn("type", result)
        self.assertIn("nudge_type", result)
        self.assertIn("priority", result)
        self.assertIn("message", result)
        self.assertIn("action", result)
        self.assertEqual(result["type"], "health")


class TestOverdueMedNudge(TestCase):
    """Overdue medications always trigger HIGH nudge."""

    def test_overdue_triggers_nudge(self):
        summary = _summary(
            [_item("medications_overdue", "high", "2 meds overdue")],
            priority_level="high",
            flags={"has_medication_risk": True, "has_urgent": True},
        )
        coaching = _coaching("Take your medications now")
        result = generate_health_nudge(summary, [], coaching, _now())
        self.assertIsNotNone(result)
        self.assertEqual(result["nudge_type"], NUDGE_MED_OVERDUE)
        self.assertEqual(result["priority"], "high")
        self.assertIn("overdue", result["message"].lower())

    def test_overdue_respects_frequency(self):
        now = _now()
        summary = _summary(
            [_item("medications_overdue", "high", "2 meds overdue")],
            priority_level="high",
            flags={"has_medication_risk": True},
        )
        coaching = _coaching("Take meds now")
        # Last sent 30 minutes ago (within 60-min limit)
        last_nudges = {NUDGE_MED_OVERDUE: (now - timedelta(minutes=30)).isoformat()}
        result = generate_health_nudge(summary, [], coaching, now, last_nudges)
        self.assertIsNone(result)

    def test_overdue_sends_after_frequency_expires(self):
        now = _now()
        summary = _summary(
            [_item("medications_overdue", "high", "2 meds overdue")],
            priority_level="high",
            flags={"has_medication_risk": True},
        )
        coaching = _coaching("Take meds now")
        # Last sent 90 minutes ago (outside 60-min limit)
        last_nudges = {NUDGE_MED_OVERDUE: (now - timedelta(minutes=90)).isoformat()}
        result = generate_health_nudge(summary, [], coaching, now, last_nudges)
        self.assertIsNotNone(result)
        self.assertEqual(result["nudge_type"], NUDGE_MED_OVERDUE)


class TestSignalDeclineNudge(TestCase):
    """Declining signals trigger MEDIUM nudge."""

    def test_declining_signal_triggers(self):
        summary = _summary(
            [_item("bp_normal", "low", "BP ok")],
            priority_level="low",
        )
        signals = [
            {"key": "activity_momentum", "state": "low", "trend": "declining",
             "insight": "Activity levels are trending down this week"},
        ]
        coaching = _coaching("Take a 10-minute walk")
        result = generate_health_nudge(summary, signals, coaching, _now())
        self.assertIsNotNone(result)
        self.assertEqual(result["nudge_type"], NUDGE_SIGNAL_DECLINE)
        self.assertEqual(result["priority"], "medium")

    def test_stable_signal_no_nudge(self):
        summary = _summary(
            [_item("bp_normal", "low", "BP ok")],
            priority_level="low",
        )
        signals = [
            {"key": "sleep_recovery", "state": "strong", "trend": "stable",
             "insight": "Sleep has been strong this week"},
        ]
        coaching = _coaching()
        result = generate_health_nudge(summary, signals, coaching, _now())
        # Should fall through to reinforcement, not signal decline
        if result:
            self.assertNotEqual(result["nudge_type"], NUDGE_SIGNAL_DECLINE)

    def test_signal_respects_daily_frequency(self):
        now = _now()
        summary = _summary([_item("bp_normal", "low", "ok")])
        signals = [
            {"key": "activity_momentum", "state": "declining", "trend": "declining",
             "insight": "Activity down"},
        ]
        coaching = _coaching("Walk")
        # Last sent 6 hours ago (within 24-hour limit)
        nudge_key = f"{NUDGE_SIGNAL_DECLINE}_activity_momentum"
        last_nudges = {nudge_key: (now - timedelta(hours=6)).isoformat()}
        result = generate_health_nudge(summary, signals, coaching, now, last_nudges)
        # Should skip signal decline, may fall through to reinforcement
        if result:
            self.assertNotEqual(result["nudge_key"], nudge_key)

    def test_signal_priority_order(self):
        """med_adherence wins over sleep_recovery."""
        summary = _summary([_item("bp_normal", "low", "ok")])
        signals = [
            {"key": "sleep_recovery", "state": "poor", "trend": "declining",
             "insight": "Sleep has been poor"},
            {"key": "med_adherence", "state": "poor", "trend": "declining",
             "insight": "Medication adherence declining"},
        ]
        coaching = _coaching("Set a reminder")
        result = generate_health_nudge(summary, signals, coaching, _now())
        self.assertIsNotNone(result)
        self.assertIn("med_adherence", result["nudge_key"])


class TestReinforcementNudge(TestCase):
    """Stable state generates LOW reinforcement nudge."""

    def test_stable_triggers_reinforcement(self):
        summary = _summary(
            [_item("bp_normal", "low", "BP ok"),
             _item("sleep_strong", "low", "Sleep ok")],
            priority_level="low",
            flags={"has_positive": True},
        )
        coaching = _coaching("Stay consistent with your routine today")
        result = generate_health_nudge(summary, [], coaching, _now())
        self.assertIsNotNone(result)
        self.assertEqual(result["nudge_type"], NUDGE_REINFORCEMENT)
        self.assertEqual(result["priority"], "low")

    def test_reinforcement_respects_daily_frequency(self):
        now = _now()
        summary = _summary(
            [_item("bp_normal", "low", "BP ok")],
            priority_level="low",
        )
        coaching = _coaching()
        last_nudges = {NUDGE_REINFORCEMENT: (now - timedelta(hours=6)).isoformat()}
        result = generate_health_nudge(summary, [], coaching, now, last_nudges)
        self.assertIsNone(result)

    def test_no_reinforcement_when_urgent(self):
        summary = _summary(
            [_item("medications_overdue", "high", "2 meds overdue")],
            priority_level="high",
            flags={"has_urgent": True, "has_medication_risk": True},
        )
        coaching = _coaching("Take meds now")
        result = generate_health_nudge(summary, [], coaching, _now())
        # Should be med overdue, not reinforcement
        if result:
            self.assertNotEqual(result["nudge_type"], NUDGE_REINFORCEMENT)


class TestNoNudgeNeeded(TestCase):
    """No nudge when everything is suppressed by frequency."""

    def test_all_suppressed(self):
        now = _now()
        summary = _summary(
            [_item("bp_normal", "low", "ok")],
            priority_level="low",
        )
        coaching = _coaching()
        # All nudge types sent recently
        last_nudges = {
            NUDGE_MED_OVERDUE: (now - timedelta(minutes=10)).isoformat(),
            NUDGE_REINFORCEMENT: (now - timedelta(hours=1)).isoformat(),
        }
        result = generate_health_nudge(summary, [], coaching, now, last_nudges)
        self.assertIsNone(result)

    def test_empty_signals_no_crash(self):
        summary = _summary([_item("bp_normal", "low", "ok")])
        coaching = _coaching()
        result = generate_health_nudge(summary, None, coaching, _now())
        # Should work (reinforcement or None)
        if result:
            self.assertEqual(result["type"], "health")
