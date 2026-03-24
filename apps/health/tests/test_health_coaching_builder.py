# ==============================================================================
# File: apps/health/tests/test_health_coaching_builder.py
# Description: Tests for deterministic health coaching builder
# ==============================================================================

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.health.services.health_coaching_builder import (
    build_health_coaching,
    apply_time_awareness,
)


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

    def test_returns_fallback_on_empty_summary(self):
        """Safety fallback: always returns a valid coaching dict."""
        result = build_health_coaching({})
        self.assertIsNotNone(result)
        self.assertIn("consistent", result["action"].lower())

    def test_returns_fallback_on_no_items(self):
        result = build_health_coaching({"items": []})
        self.assertIsNotNone(result)
        self.assertIn("consistent", result["action"].lower())

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


# ── Time-Aware Coaching ─────────────────────────────────────────────────────

def _dt(hour=12, minute=0):
    """Build an aware datetime at a specific hour."""
    return timezone.now().replace(hour=hour, minute=minute, second=0, microsecond=0)


def _next_event_in(minutes, current_dt):
    """Build an ISO timestamp `minutes` from current_dt."""
    return (current_dt + timedelta(minutes=minutes)).isoformat()


class TestTimeAwarenessNone(TestCase):
    """Handles None/missing gracefully."""

    def test_none_coaching(self):
        self.assertIsNone(apply_time_awareness(None, _dt()))

    def test_none_current_dt(self):
        coaching = {"action": "Walk", "reason": "Good", "source_key": "activity_low",
                    "priority_level": "medium"}
        result = apply_time_awareness(coaching, None)
        self.assertEqual(result["action"], "Walk")


class TestMedicationNeverDelayed(TestCase):
    """Medications overdue always say 'now', never delayed."""

    def test_overdue_always_now(self):
        coaching = {"action": "Take your medications now", "reason": "Overdue",
                    "source_key": "medications_overdue", "priority_level": "high"}
        # Even with an event in 10 minutes
        result = apply_time_awareness(coaching, _dt(14), _next_event_in(10, _dt(14)))
        self.assertIn("now", result["action"].lower())
        self.assertNotIn("after", result["action"].lower())

    def test_overdue_now_appended_if_missing(self):
        coaching = {"action": "Take your medications", "reason": "Overdue",
                    "source_key": "medications_overdue", "priority_level": "high"}
        result = apply_time_awareness(coaching, _dt())
        self.assertIn("now", result["action"].lower())

    def test_critical_bp_never_delayed(self):
        coaching = {"action": "Sit down and rest", "reason": "BP high",
                    "source_key": "bp_crisis", "priority_level": "high"}
        result = apply_time_awareness(coaching, _dt(), _next_event_in(10, _dt()))
        self.assertNotIn("after", result["action"].lower())


class TestFreeWindow(TestCase):
    """No upcoming event = add 'now' for actionable items."""

    def test_adds_now_when_free(self):
        coaching = {"action": "Take a 10-minute walk", "reason": "Activity low",
                    "source_key": "activity_low", "priority_level": "medium"}
        result = apply_time_awareness(coaching, _dt(14), None)
        self.assertIn("now", result["action"].lower())

    def test_adds_now_when_event_far(self):
        coaching = {"action": "Take a 10-minute walk", "reason": "Activity low",
                    "source_key": "activity_low", "priority_level": "medium"}
        result = apply_time_awareness(coaching, _dt(14), _next_event_in(90, _dt(14)))
        self.assertIn("now", result["action"].lower())

    def test_no_now_for_reinforcement(self):
        coaching = {"action": "Stay consistent with your routine", "reason": "Stable",
                    "source_key": "bp_normal", "priority_level": "low"}
        result = apply_time_awareness(coaching, _dt(14), None)
        self.assertNotIn("now", result["action"].lower())


class TestBusySoon(TestCase):
    """Event within 30 minutes = defer to 'after your next task finishes'."""

    def test_shifts_to_after_task(self):
        coaching = {"action": "Take a 10-minute walk", "reason": "Low activity",
                    "source_key": "activity_low", "priority_level": "medium"}
        result = apply_time_awareness(coaching, _dt(14), _next_event_in(15, _dt(14)))
        self.assertIn("after your next task finishes", result["action"].lower())

    def test_no_defer_for_reinforcement(self):
        coaching = {"action": "Stay consistent with your routine", "reason": "Stable",
                    "source_key": "bp_normal", "priority_level": "low"}
        result = apply_time_awareness(coaching, _dt(14), _next_event_in(15, _dt(14)))
        self.assertNotIn("after", result["action"].lower())


class TestEvening(TestCase):
    """Evening time block softens activity actions."""

    def test_walk_softened_in_evening(self):
        coaching = {"action": "Take a 10-minute walk", "reason": "Activity low",
                    "source_key": "activity_low", "priority_level": "medium"}
        result = apply_time_awareness(coaching, _dt(20), None)
        self.assertIn("evening", result["action"].lower())
        self.assertIn("short walk", result["action"].lower())

    def test_non_activity_not_softened_in_evening(self):
        coaching = {"action": "Aim for an earlier bedtime tonight", "reason": "Short sleep",
                    "source_key": "sleep_short", "priority_level": "medium"}
        result = apply_time_awareness(coaching, _dt(20), None)
        # Sleep coaching should not be changed to "evening walk"
        self.assertIn("bedtime", result["action"].lower())


class TestStableDay(TestCase):
    """Stable/reinforcement items get 'today' appended."""

    def test_adds_today_to_reinforcement(self):
        coaching = {"action": "Stay consistent with your routine", "reason": "Stable",
                    "source_key": "bp_normal", "priority_level": "low"}
        result = apply_time_awareness(coaching, _dt(14), None)
        self.assertIn("today", result["action"].lower())

    def test_no_double_today(self):
        coaching = {"action": "Keep it going today", "reason": "Stable",
                    "source_key": "medications_on_track", "priority_level": "low"}
        result = apply_time_awareness(coaching, _dt(14), None)
        self.assertEqual(result["action"].lower().count("today"), 1)


# ── FIX 1: Action eligibility ───────────────────────────────────────────────

class TestActionEligibility(TestCase):
    """Completed actions are never recommended."""

    def test_safety_fallback_on_empty(self):
        """build_health_coaching always returns valid coaching."""
        result = build_health_coaching(None)
        self.assertIsNotNone(result)
        self.assertIn("action", result)

    def test_falls_to_next_item_when_primary_ineligible(self):
        """If overdue meds key is present but no longer in items, skip."""
        # This tests the loop logic — items are in order, first valid wins
        summary = _summary([
            _item("bp_elevated", "medium", "Blood pressure is elevated"),
        ], priority_level="medium")
        result = build_health_coaching(summary)
        self.assertEqual(result["source_key"], "bp_elevated")


# ── FIX 3: Signal language consistency ──────────────────────────────────────

class TestSignalLanguage(TestCase):
    """All signal-derived reasons use 'this week', never 'lately'."""

    def test_sleep_short_reason_says_this_week(self):
        summary = _summary([_item("sleep_short", "medium", "Sleep has been short")])
        result = build_health_coaching(summary)
        self.assertIn("this week", result["reason"])
        self.assertNotIn("lately", result["reason"])

    def test_activity_low_reason_says_this_week(self):
        summary = _summary([_item("activity_low", "medium", "Activity low")])
        result = build_health_coaching(summary)
        self.assertIn("this week", result["reason"])

    def test_signal_activity_declining_says_this_week(self):
        summary = _summary([
            _item("signal_activity_momentum", "medium",
                  "Activity levels trending down", "signal"),
        ], priority_level="medium")
        signals = [
            {"key": "activity_momentum", "state": "declining",
             "insight": "Activity has been dropping this week"},
        ]
        result = build_health_coaching(summary, signals)
        self.assertIn("this week", result["reason"])


# ── FIX 4: Safety fallback ──────────────────────────────────────────────────

class TestSafetyFallback(TestCase):
    """System NEVER returns empty or None coaching."""

    def test_always_returns_dict(self):
        result = build_health_coaching({})
        self.assertIsInstance(result, dict)
        self.assertIn("action", result)

    def test_fallback_has_today(self):
        result = build_health_coaching({"items": []})
        self.assertIn("today", result["action"].lower())
