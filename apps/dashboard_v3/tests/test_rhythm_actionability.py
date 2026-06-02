"""
Rhythm actionability regression tests — "a day is not over until midnight".

Proves that today's rhythm items stay completable past their scheduled time:
mass-complete (dose_groups) buttons survive into past-today blocks, individual
items keep their toggle_url, future blocks stay preview-only, and the wording
is encouraging ("Behind") rather than punitive ("Missed" / "Past due").

These are presentation-layer tests against build_rhythm_sections — items are
fed in via an explicit execution_contract so no DB scheduling is needed; the
current wall-clock block is forced by patching get_user_now.
"""

from datetime import datetime
from unittest.mock import patch

from django.test import TestCase

from apps.core.cos_briefing.rhythm import (
    RHYTHM_EXPIRATION_MODE_DEFAULT,
    _block_actionable,
    build_rhythm_sections,
)
from apps.users.models import User


def _med_item(title, window, scheduled_time, completed=False, urgency="next"):
    return {
        "source_type": "medication_dose",
        "source_id": f"{title}-{window}",
        "title": title,
        "domain": "health",
        "intake_type": "medication",
        "time_of_day": window,
        "execution_group_id": window,
        "scheduled_time": scheduled_time,
        "completed_today": completed,
        "is_actionable": not completed,
        "urgency": urgency,
        "toggle_url": f"/dashboard/actions/intake/1/log/",
        "detail_url": "",
    }


def _routine_item(title, window, scheduled_time, completed=False):
    return {
        "source_type": "routine_item",
        "source_id": f"{title}-{window}",
        "title": title,
        "domain": "life",
        "time_of_day": window,
        "scheduled_time": scheduled_time,
        "completed_today": completed,
        "is_actionable": not completed,
        "toggle_url": "/dashboard/actions/routine/schedule/1/toggle/",
        "detail_url": "/life/routines/",
    }


def _now_at(hour):
    return datetime(2026, 6, 2, hour, 0, 0)


def _section(result, key):
    for s in result["sections"]:
        if s["key"] == key:
            return s
    raise AssertionError(f"no rhythm section {key!r}")


class BlockActionableHelperTests(TestCase):
    def test_default_mode_is_end_of_day(self):
        self.assertEqual(RHYTHM_EXPIRATION_MODE_DEFAULT, "END_OF_DAY")

    def test_current_and_past_are_actionable_future_is_not(self):
        # is_future=False covers both current and past today blocks.
        self.assertTrue(_block_actionable(is_future=False))
        self.assertFalse(_block_actionable(is_future=True))


class RhythmActionabilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="rhythm-actionable@example.com", password="x"
        )

    def _build(self, items, now_hour):
        contract = {"items": items, "summaries": {}}
        with patch(
            "apps.core.utils.get_user_now", return_value=_now_at(now_hour)
        ):
            return build_rhythm_sections(self.user, execution_contract=contract)

    def test_past_today_block_keeps_mass_complete_buttons(self):
        """A 6 AM medication group is still mass-completable at 7 PM."""
        items = [
            _med_item("Metformin", "morning", "06:00"),
            _med_item("Lisinopril", "morning", "06:00"),
        ]
        result = self._build(items, now_hour=19)  # evening → morning is past
        morning = _section(result, "morning")

        self.assertTrue(morning["is_past"])
        self.assertEqual(morning["interaction_mode"], "summary")
        self.assertTrue(
            morning["dose_groups"],
            "past-today block must keep its mass-complete dose groups",
        )
        grp = morning["dose_groups"][0]
        self.assertEqual(grp["open_count"], 2)

    def test_past_today_individual_item_stays_actionable(self):
        """A 6:30 AM shower routine keeps its toggle_url at 7 PM."""
        items = [_routine_item("Shower", "morning", "06:30")]
        result = self._build(items, now_hour=19)
        morning = _section(result, "morning")
        item = morning["items"][0]

        self.assertFalse(item["completed_today"])
        self.assertTrue(item["toggle_url"], "completion link must survive past time")
        self.assertTrue(item["is_actionable"])

    def test_future_block_has_no_mass_complete(self):
        """Evening doses in the morning are preview-only — not yet actionable."""
        items = [_med_item("Statin", "evening", "19:00")]
        result = self._build(items, now_hour=7)  # morning → evening is future
        evening = _section(result, "evening")

        self.assertFalse(evening["is_past"])
        self.assertFalse(evening["is_current"])
        self.assertEqual(evening["dose_groups"], [])
        self.assertIn(evening["interaction_mode"], ("preview", "empty"))

    def test_current_block_still_has_mass_complete(self):
        """Regression: the active block keeps full controls."""
        items = [_med_item("Metformin", "morning", "06:00")]
        result = self._build(items, now_hour=7)
        morning = _section(result, "morning")

        self.assertTrue(morning["is_current"])
        self.assertEqual(morning["interaction_mode"], "full")
        self.assertTrue(morning["dose_groups"])

    def test_past_block_uses_behind_language_not_punitive(self):
        items = [_routine_item("Shower", "morning", "06:30")]
        result = self._build(items, now_hour=19)
        morning = _section(result, "morning")

        self.assertEqual(morning["open_label"], "Behind — still available today")
        blob = (morning["open_label"] + " " + morning["momentum"]).lower()
        self.assertNotIn("missed", blob)
        self.assertNotIn("past due", blob)

    def test_past_overdue_momentum_says_behind(self):
        items = [
            _med_item("Metformin", "morning", "06:00", urgency="overdue"),
            _med_item("Lisinopril", "morning", "06:00", urgency="overdue"),
        ]
        result = self._build(items, now_hour=19)
        morning = _section(result, "morning")
        self.assertIn("behind", morning["momentum"].lower())
        self.assertNotIn("past due", morning["momentum"].lower())
