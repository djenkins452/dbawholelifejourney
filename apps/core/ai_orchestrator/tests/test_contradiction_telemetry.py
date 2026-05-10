"""Tests for the rollup-vs-canonical contradiction detector."""

from django.test import SimpleTestCase

from apps.core.ai_orchestrator.contradiction_telemetry import (
    detect_contradictions,
)


def _routine(item_id, title, *, completed=False):
    return {
        "source_type": "routine_item",
        "source_id": item_id,
        "title": title,
        "completed_today": completed,
        "is_actionable": not completed,
        "completion_status": "completed" if completed else "pending",
    }


class ContradictionTelemetryTests(SimpleTestCase):

    def test_prayer_rollup_vs_items_detected(self):
        state = {
            "items": [_routine(1, "Prayer Time", completed=False)],
            "summaries": {
                "domains": {"prayer": True, "bible_reading": False},
                "medications": {},
            },
        }
        out = detect_contradictions(
            exec_state=state, fresh_med_schedule=None,
            user_id=42, request_id="r1",
        )
        codes = [c.code for c in out]
        self.assertIn("PRAYER_ROLLUP_VS_ITEMS", codes)

    def test_no_contradiction_when_aligned(self):
        state = {
            "items": [_routine(1, "Prayer Time", completed=True)],
            "summaries": {
                "domains": {"prayer": True, "bible_reading": False},
                "medications": {},
            },
        }
        out = detect_contradictions(
            exec_state=state, fresh_med_schedule=None,
        )
        self.assertEqual(out, [])

    def test_bible_rollup_vs_items_detected(self):
        state = {
            "items": [_routine(2, "Bible Reading", completed=False)],
            "summaries": {
                "domains": {"prayer": False, "bible_reading": True},
                "medications": {},
            },
        }
        out = detect_contradictions(exec_state=state)
        codes = [c.code for c in out]
        self.assertIn("BIBLE_ROLLUP_VS_ITEMS", codes)

    def test_medication_window_vs_dose_detected(self):
        state = {
            "items": [],
            "summaries": {
                "domains": {},
                "medications": {
                    "medication_window_morning": {
                        "label": "Morning Medications",
                        "all_taken": True,
                        "taken": 2, "total": 3,
                    },
                },
            },
        }
        fresh = [
            {"window_label": "morning", "medicine_name": "Lantus",
             "scheduled_time": "08:00", "status": "pending"},
            {"window_label": "morning", "medicine_name": "Metformin",
             "scheduled_time": "08:00", "status": "taken"},
            {"window_label": "morning", "medicine_name": "B12",
             "scheduled_time": "08:00", "status": "taken"},
        ]
        out = detect_contradictions(
            exec_state=state, fresh_med_schedule=fresh,
        )
        codes = [c.code for c in out]
        self.assertIn("MEDICATION_WINDOW_VS_DOSE", codes)

    def test_workout_rollup_vs_items_detected(self):
        state = {
            "items": [_routine(3, "Morning Workout", completed=False)],
            "summaries": {
                "domains": {"workout": True},
                "medications": {},
            },
        }
        out = detect_contradictions(exec_state=state)
        codes = [c.code for c in out]
        self.assertIn("WORKOUT_ROLLUP_VS_ITEMS", codes)

    def test_no_contradiction_for_completed_workout(self):
        state = {
            "items": [_routine(3, "Morning Workout", completed=True)],
            "summaries": {
                "domains": {"workout": True},
                "medications": {},
            },
        }
        out = detect_contradictions(exec_state=state)
        self.assertEqual(out, [])
