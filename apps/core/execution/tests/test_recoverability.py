"""Tests for the deterministic recoverability check, including the
hard cutoff at the next anchor block start for WINDOWED items."""

import datetime as dt

from django.test import SimpleTestCase

from apps.core.execution.recoverability import is_recoverable, recovery_cutoff
from apps.core.execution.task_classifier import (
    FLEXIBLE,
    HARD_EXPIRED,
    SOFT_EXPIRED,
    WINDOWED,
)


def _item(cls, **kw):
    return {
        'task_class': cls,
        'recovery_grace_minutes': kw.pop('grace', None),
        'scheduled_time': kw.pop('scheduled_time', None),
        **kw,
    }


class RecoverabilityTests(SimpleTestCase):

    # ── HARD_EXPIRED ───────────────────────────────────────────────
    def test_hard_expired_recoverable_before_scheduled(self):
        item = _item(HARD_EXPIRED, scheduled_time='10:30', grace=0)
        self.assertTrue(is_recoverable(item, dt.time(10, 0)))

    def test_hard_expired_recoverable_at_scheduled(self):
        item = _item(HARD_EXPIRED, scheduled_time='10:30', grace=0)
        self.assertTrue(is_recoverable(item, dt.time(10, 30)))

    def test_hard_expired_not_recoverable_after_scheduled(self):
        item = _item(HARD_EXPIRED, scheduled_time='10:30', grace=0)
        self.assertFalse(is_recoverable(item, dt.time(14, 10)))

    # ── WINDOWED with hard cutoff ──────────────────────────────────
    def test_windowed_recoverable_inside_grace_and_window(self):
        # Protein shake 6:45 AM, 90 min grace. At 8:00 AM still inside
        # both grace (8:15) and morning window (ends 10:00).
        item = _item(WINDOWED, scheduled_time='06:45', grace=90)
        self.assertTrue(is_recoverable(item, dt.time(8, 0)))

    def test_windowed_not_recoverable_past_grace(self):
        # 6:45 + 90 = 8:15. At 8:30 grace is gone.
        item = _item(WINDOWED, scheduled_time='06:45', grace=90)
        self.assertFalse(is_recoverable(item, dt.time(8, 30)))

    def test_windowed_not_recoverable_past_next_anchor_even_if_grace_long(self):
        # Critical med 8:00 AM with 60 min grace would put cutoff at
        # 9:00 AM — still inside morning window. But what about a
        # WINDOWED item with very long grace? Use synthetic 300 min
        # grace from 6:45 (sched). Grace would say 11:45 cutoff, but
        # next anchor (mid_morning starts 10:00) caps it at 10:00.
        item = _item(WINDOWED, scheduled_time='06:45', grace=300)
        self.assertTrue(is_recoverable(item, dt.time(9, 59)))
        self.assertFalse(is_recoverable(item, dt.time(10, 0)))

    def test_protein_shake_not_recoverable_at_2_10_pm(self):
        # The canonical scenario: morning protein shake at 6:45,
        # checked at 14:10 — must be non-recoverable.
        item = _item(WINDOWED, scheduled_time='06:45', grace=90)
        self.assertFalse(is_recoverable(item, dt.time(14, 10)))

    # ── SOFT_EXPIRED ───────────────────────────────────────────────
    def test_soft_expired_recoverable_all_day(self):
        item = _item(SOFT_EXPIRED, scheduled_time='07:00', grace=None)
        self.assertTrue(is_recoverable(item, dt.time(14, 10)))
        self.assertTrue(is_recoverable(item, dt.time(22, 0)))

    # ── FLEXIBLE ───────────────────────────────────────────────────
    def test_flexible_recoverable_always(self):
        item = _item(FLEXIBLE, scheduled_time=None)
        self.assertTrue(is_recoverable(item, dt.time(14, 10)))

    # ── Cutoff helper ──────────────────────────────────────────────
    def test_recovery_cutoff_clamps_to_next_anchor(self):
        item = _item(WINDOWED, scheduled_time='06:45', grace=300)
        cutoff = recovery_cutoff(item)
        # Next anchor (mid_morning) starts at 10:00.
        self.assertEqual(cutoff, dt.time(10, 0))

    def test_recovery_cutoff_uses_grace_when_inside_window(self):
        item = _item(WINDOWED, scheduled_time='06:45', grace=60)
        # 6:45 + 60 = 7:45, still inside morning window.
        self.assertEqual(recovery_cutoff(item), dt.time(7, 45))

    def test_recovery_cutoff_none_for_soft_and_flexible(self):
        self.assertIsNone(recovery_cutoff(_item(SOFT_EXPIRED)))
        self.assertIsNone(recovery_cutoff(_item(FLEXIBLE)))

    def test_unscheduled_windowed_falls_through(self):
        item = _item(WINDOWED, scheduled_time=None, grace=90)
        # Without a scheduled time we cannot evaluate the cutoff;
        # safe default = recoverable.
        self.assertTrue(is_recoverable(item, dt.time(14, 10)))
