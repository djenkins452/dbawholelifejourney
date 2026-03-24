# ==============================================================================
# File: apps/health/tests/test_health_coaching_builder.py
# Description: Tests for deterministic health coaching builder
# ==============================================================================

from django.test import TestCase

from apps.health.services.health_coaching_builder import build_health_coaching


def _summary(items, priority_level="low", headline="Health looks stable"):
    return {
        "headline": headline,
        "priority_level": priority_level,
        "items": items,
        "flags": {},
        "generated_at": "2026-03-24T12:00:00",
    }


def _item(key, priority, message, category="vitals"):
    return {"key": key, "priority": priority, "message": message,
            "category": category, "icon": "heart"}


class TestCoachingContract(TestCase):
    """Output contract tests."""

    def test_returns_none_on_empty_summary(self):
        self.assertIsNone(build_health_coaching({}))

    def test_returns_none_on_no_items(self):
        self.assertIsNone(build_health_coaching({"items": []}))

    def test_returns_dict_with_required_keys(self):
        summary = _summary([_item("bp_normal", "low", "Blood pressure looks good")])
        result = build_health_coaching(summary)
        self.assertIn("action", result)
        self.assertIn("reason", result)
        self.assertIn("priority_level", result)
        self.assertIn("source_key", result)

    def test_exactly_one_action(self):
        summary = _summary([
            _item("medications_overdue", "high", "2 medications overdue", "medical"),
            _item("bp_elevated", "medium", "Blood pressure is elevated"),
        ], priority_level="high")
        result = build_health_coaching(summary)
        # Should have exactly one action string, not a list
        self.assertIsInstance(result["action"], str)


class TestMedicationDominance(TestCase):
    """Medications overdue MUST always produce 'take medications' action."""

    def test_overdue_meds_action(self):
        summary = _summary([
            _item("medications_overdue", "high", "2 medications overdue", "medical"),
            _item("bp_elevated", "medium", "Blood pressure is elevated"),
        ], priority_level="high")
        result = build_health_coaching(summary)
        self.assertIn("medications", result["action"].lower())
        self.assertEqual(result["source_key"], "medications_overdue")

    def test_overdue_meds_override_everything(self):
        summary = _summary([
            _item("medications_overdue", "high", "3 medications overdue", "medical"),
            _item("bp_crisis", "high", "Blood pressure is very high"),
        ], priority_level="high")
        result = build_health_coaching(summary)
        self.assertEqual(result["source_key"], "medications_overdue")


class TestHighPriority(TestCase):

    def test_bp_crisis(self):
        summary = _summary([
            _item("bp_crisis", "high", "Blood pressure is very high"),
        ], priority_level="high")
        result = build_health_coaching(summary)
        self.assertIn("rest", result["action"].lower())

    def test_glucose_severe(self):
        summary = _summary([
            _item("glucose_severe", "high", "Blood sugar needs attention"),
        ], priority_level="high")
        result = build_health_coaching(summary)
        self.assertIn("blood sugar", result["reason"].lower())


class TestMediumPriority(TestCase):

    def test_bp_elevated(self):
        summary = _summary([
            _item("bp_elevated", "medium", "Blood pressure is elevated"),
        ], priority_level="medium")
        result = build_health_coaching(summary)
        self.assertIn("slow down", result["action"].lower())

    def test_sleep_short(self):
        summary = _summary([
            _item("sleep_short", "medium", "Sleep has been short lately"),
        ], priority_level="medium")
        result = build_health_coaching(summary)
        self.assertIn("bedtime", result["action"].lower())

    def test_activity_low(self):
        summary = _summary([
            _item("activity_low", "medium", "Activity has been low lately"),
        ], priority_level="medium")
        result = build_health_coaching(summary)
        self.assertIn("walk", result["action"].lower())


class TestLowPriority(TestCase):

    def test_stable_reinforcement(self):
        summary = _summary([
            _item("bp_normal", "low", "Blood pressure looks good"),
            _item("sleep_strong", "low", "Sleep has been strong"),
        ])
        result = build_health_coaching(summary)
        self.assertIn("consistent", result["action"].lower())

    def test_meds_on_track(self):
        summary = _summary([
            _item("medications_on_track", "low", "Medications are on track", "medical"),
        ])
        result = build_health_coaching(summary)
        self.assertIn("consistent", result["action"].lower())


class TestSignalIntegration(TestCase):
    """Signal-based items use signal actions."""

    def test_signal_activity_declining(self):
        summary = _summary([
            _item("signal_activity_momentum", "medium",
                  "Activity levels are trending down this week", "signal"),
        ], priority_level="medium")
        signals = [
            {"key": "activity_momentum", "state": "low", "trend": "declining",
             "insight": "Activity levels are trending down this week"},
        ]
        result = build_health_coaching(summary, signals)
        self.assertIn("walk", result["action"].lower())

    def test_signal_cardio_unstable(self):
        summary = _summary([
            _item("signal_cardio_stability", "high",
                  "Multiple vital signs need attention", "signal"),
        ], priority_level="high")
        signals = [
            {"key": "cardio_stability", "state": "unstable",
             "insight": "Multiple vital signs need attention"},
        ]
        result = build_health_coaching(summary, signals)
        self.assertIn("rest", result["action"].lower())


class TestFallback(TestCase):
    """Unknown keys still produce a valid action."""

    def test_unknown_key_high_priority(self):
        summary = _summary([
            _item("unknown_future_metric", "high", "Something needs attention"),
        ], priority_level="high")
        result = build_health_coaching(summary)
        self.assertIsNotNone(result)
        self.assertIn("action", result)

    def test_unknown_key_low_priority(self):
        summary = _summary([
            _item("unknown_metric", "low", "Something is fine"),
        ])
        result = build_health_coaching(summary)
        self.assertIsNotNone(result)
        self.assertIn("consistent", result["action"].lower())


class TestNoSignals(TestCase):
    """Works correctly without signals."""

    def test_none_signals(self):
        summary = _summary([
            _item("bp_normal", "low", "Blood pressure looks good"),
        ])
        result = build_health_coaching(summary, signals=None)
        self.assertIsNotNone(result)
