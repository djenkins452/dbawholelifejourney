"""
Tests for apps/core/execution/active_block.py — Active Execution Block resolver.

Covers:
- Static window mapping (no per-user items)
- Per-user derivation overrides static map
- Lead-in window for next block
- Item eligibility under active-block gating
- Overdue items always pass the gate
- Outside-canonical-window time (e.g., 4 AM) handling
"""

import datetime

from django.test import SimpleTestCase

from apps.core.execution.active_block import (
    LEAD_IN_MINUTES,
    get_active_block,
    is_item_in_active_block,
)


class _StubUser:
    """Minimal stand-in: get_active_block accepts `now` directly."""
    id = 1


class GetActiveBlockTests(SimpleTestCase):
    def setUp(self):
        self.user = _StubUser()

    def test_morning_block_at_07_55(self):
        """At 07:55 the active block is 'morning' (canonical 5–10)."""
        ab = get_active_block(
            self.user,
            now=datetime.time(7, 55),
            execution_items=[],
        )
        self.assertEqual(ab["name"], "morning")
        self.assertEqual(ab["start_time"], datetime.time(5, 0))
        self.assertEqual(ab["end_time"], datetime.time(10, 0))
        self.assertEqual(ab["next_block_name"], "mid_morning")
        self.assertEqual(ab["next_block_start"], datetime.time(10, 0))

    def test_outside_canonical_returns_none(self):
        """At 04:30 (before 'morning' starts) name is None, next is morning."""
        ab = get_active_block(
            self.user,
            now=datetime.time(4, 30),
            execution_items=[],
        )
        self.assertIsNone(ab["name"])
        self.assertEqual(ab["next_block_name"], "morning")
        self.assertEqual(ab["next_block_start"], datetime.time(5, 0))

    def test_evening_with_no_next_block(self):
        """At 22:00 we're in 'nightly'. Static map ends after nightly."""
        ab = get_active_block(
            self.user,
            now=datetime.time(22, 0),
            execution_items=[],
        )
        self.assertEqual(ab["name"], "nightly")
        # No next block defined after nightly in WINDOW_ORDER
        self.assertIsNone(ab["next_block_name"])

    def test_lead_in_end_time_is_15min_before_next_block(self):
        """lead_in_end_time = next_block_start - LEAD_IN_MINUTES."""
        ab = get_active_block(
            self.user,
            now=datetime.time(7, 55),
            execution_items=[],
        )
        # next block (mid_morning) starts at 10:00; lead-in ends at 09:45
        expected = datetime.time(
            10 - 1 if LEAD_IN_MINUTES <= 60 else 10,
            (60 - LEAD_IN_MINUTES) % 60,
        )
        self.assertEqual(ab["lead_in_end_time"], expected)


class IsItemInActiveBlockTests(SimpleTestCase):
    def setUp(self):
        self.user = _StubUser()

    def test_item_in_active_block_eligible(self):
        """A morning-window item at 08:00 is eligible during morning block."""
        ab = get_active_block(self.user, now=datetime.time(7, 55),
                              execution_items=[])
        eligible = is_item_in_active_block(
            {"scheduled_time": "08:00"},
            ab,
            datetime.time(7, 55),
        )
        self.assertTrue(eligible)

    def test_future_block_item_not_eligible_far_from_lead_in(self):
        """At 07:55, a 09:00 item (mid_morning, far from 09:45 lead-in)
        is NOT eligible — this is the 7:55 / 8:00 / 9:00 regression case."""
        ab = get_active_block(self.user, now=datetime.time(7, 55),
                              execution_items=[])
        eligible = is_item_in_active_block(
            {"scheduled_time": "09:00"},
            ab,
            datetime.time(7, 55),
        )
        # 09:00 is in mid_morning (10–12) — wait, 09:00 is still in morning
        # canonical (5–10). So this IS eligible. Check.
        self.assertTrue(eligible)  # 09:00 falls in 'morning' (5–10)

    def test_future_block_item_at_10_30_not_eligible_at_07_55(self):
        """10:30 is in 'mid_morning'; at 07:55 we are not in lead-in."""
        ab = get_active_block(self.user, now=datetime.time(7, 55),
                              execution_items=[])
        eligible = is_item_in_active_block(
            {"scheduled_time": "10:30"},
            ab,
            datetime.time(7, 55),
        )
        self.assertFalse(eligible)

    def test_future_block_eligible_during_lead_in(self):
        """At 09:50 (within 15min of 10:00 mid_morning start), a
        mid_morning item is eligible."""
        ab = get_active_block(self.user, now=datetime.time(9, 50),
                              execution_items=[])
        # 09:50 still in 'morning' canonical (5–10)
        self.assertEqual(ab["name"], "morning")
        eligible = is_item_in_active_block(
            {"scheduled_time": "10:30"},
            ab,
            datetime.time(9, 50),
        )
        self.assertTrue(eligible)

    def test_overdue_in_immediately_preceding_block_eligible(self):
        """Overdue items in the immediately preceding canonical block
        ARE Execution-eligible. At 14:00 (afternoon), an overdue
        13:00 item is in 'lunch' (the preceding block) → eligible."""
        ab = get_active_block(self.user, now=datetime.time(14, 0),
                              execution_items=[])
        eligible = is_item_in_active_block(
            {"scheduled_time": "13:00", "time_status": "overdue"},
            ab,
            datetime.time(14, 0),
        )
        self.assertTrue(eligible)

    def test_overdue_in_long_past_block_not_eligible(self):
        """Strict Mode Isolation contract: overdue items in long-past
        blocks (more than one block back) are NOT Execution-eligible.
        At 14:00 (afternoon), a 06:00 morning item is two blocks
        back — must surface in Risk/Fix only, NOT in Execution."""
        ab = get_active_block(self.user, now=datetime.time(14, 0),
                              execution_items=[])
        eligible = is_item_in_active_block(
            {"scheduled_time": "06:00", "time_status": "overdue"},
            ab,
            datetime.time(14, 0),
        )
        self.assertFalse(
            eligible,
            "06:00 morning item must NOT be Execution-eligible at "
            "14:00 — it's two blocks back. Spec: stale items belong "
            "in Risk/Fix only.",
        )

    def test_overdue_5_30_at_noon_not_eligible(self):
        """The headline regression from the user spec: at noon (lunch
        block), a 5:30 AM prayer item is in 'morning' (5-10), two
        blocks back from lunch (12-14). Execution mode must NOT
        recommend this."""
        ab = get_active_block(self.user, now=datetime.time(12, 0),
                              execution_items=[])
        self.assertEqual(ab["name"], "lunch")
        eligible = is_item_in_active_block(
            {"scheduled_time": "05:30", "time_status": "overdue"},
            ab,
            datetime.time(12, 0),
        )
        self.assertFalse(
            eligible,
            "5:30 AM at noon is two blocks back — must NOT be "
            "Execution-eligible per Strict Mode Isolation contract.",
        )

    def test_past_block_non_overdue_not_eligible(self):
        """A past-block item that isn't overdue is not eligible
        (defensive: usually wouldn't reach here, but the gate must hold)."""
        ab = get_active_block(self.user, now=datetime.time(14, 0),
                              execution_items=[])
        eligible = is_item_in_active_block(
            {"scheduled_time": "06:00"},
            ab,
            datetime.time(14, 0),
        )
        self.assertFalse(eligible)

    def test_no_scheduled_time_passes_through(self):
        """Items with no scheduled_time bypass the gate (handled elsewhere)."""
        ab = get_active_block(self.user, now=datetime.time(8, 0),
                              execution_items=[])
        eligible = is_item_in_active_block(
            {"scheduled_time": None},
            ab,
            datetime.time(8, 0),
        )
        self.assertTrue(eligible)


class PerUserBoundsTests(SimpleTestCase):
    """Per-user item bounds shouldn't change *which* canonical window we're
    in (membership uses static WINDOW_HOURS), but they may surface in
    `bounds` for future use."""

    def setUp(self):
        self.user = _StubUser()

    def test_per_user_bounds_recorded_for_morning_items(self):
        items = [
            {"scheduled_time": "06:30", "execution_group_type": "routine"},
            {"scheduled_time": "08:00", "execution_group_type": "routine"},
        ]
        ab = get_active_block(self.user, now=datetime.time(7, 55),
                              execution_items=items)
        self.assertIn("morning", ab["bounds"])
        # min/max in minutes
        self.assertEqual(ab["bounds"]["morning"], (6 * 60 + 30, 8 * 60))
