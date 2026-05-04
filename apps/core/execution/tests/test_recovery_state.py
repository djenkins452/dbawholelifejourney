"""Tests for the deterministic recovery-state machine."""

import datetime as dt

from django.test import SimpleTestCase

from apps.core.execution.recovery_state import (
    NARR_BEHIND_RECOVERABLE,
    NARR_BEHIND_RESET_REQUIRED,
    NARR_DAY_LOST_SALVAGE,
    NARR_EVENING_CLOSEOUT,
    NARR_ON_TRACK,
    NORMAL,
    RECOVERY,
    SHUTDOWN,
    STABILIZE,
    compute_recovery_state,
)
from apps.core.execution.task_classifier import (
    HARD_EXPIRED,
    SOFT_EXPIRED,
    WINDOWED,
    annotate,
)


def _item(**kw):
    base = {
        'source_type': 'routine_item',
        'source_id': kw.pop('id', 1),
        'title': 'X',
        'is_actionable': True,
        'completed_today': False,
        'is_foundational': False,
        'time_status': 'overdue',
        'domain': 'life',
    }
    base.update(kw)
    return annotate(base)


class RecoveryStateTests(SimpleTestCase):

    def test_morning_on_track_is_normal(self):
        items = [_item(
            id=1, scheduled_time='09:30', time_status='upcoming',
            activity_type='workout',
        )]
        rs = compute_recovery_state(items, dt.time(9, 0))
        self.assertEqual(rs['mode'], NORMAL)
        self.assertEqual(rs['day_narrative'], NARR_ON_TRACK)

    def test_normal_with_overdue_recoverable_is_behind_recoverable(self):
        items = [
            _item(id=1, scheduled_time='09:30', activity_type='workout'),
        ]
        # 11 AM, before the noon recovery threshold, soft_expired
        # (workout) is still recoverable.
        rs = compute_recovery_state(items, dt.time(11, 0))
        self.assertEqual(rs['mode'], NORMAL)
        self.assertEqual(rs['day_narrative'], NARR_BEHIND_RECOVERABLE)

    def test_recovery_triggers_after_noon_with_two_recoverable(self):
        items = [
            _item(id=1, scheduled_time='09:30', activity_type='workout'),
            _item(id=2, scheduled_time='10:00', activity_type='journal'),
        ]
        rs = compute_recovery_state(items, dt.time(13, 0))
        self.assertEqual(rs['mode'], RECOVERY)
        self.assertEqual(rs['day_narrative'], NARR_DAY_LOST_SALVAGE)

    def test_stabilize_when_foundational_missed_and_reset_available(self):
        items = [
            # Missed foundational church (HARD_EXPIRED, not recoverable)
            _item(
                id=1, scheduled_time='10:30', activity_type='service',
                is_foundational=True,
            ),
            # Available reset action — shower (hygiene = reset)
            _item(
                id=2, scheduled_time='07:00', activity_type='hygiene',
            ),
        ]
        # 11:30 AM — before noon recovery threshold
        rs = compute_recovery_state(items, dt.time(11, 30))
        self.assertEqual(rs['mode'], STABILIZE)
        self.assertEqual(rs['day_narrative'], NARR_BEHIND_RESET_REQUIRED)
        self.assertTrue(rs['reset_action_available'])

    def test_shutdown_late_with_multiple_overdue(self):
        items = [
            _item(id=i, scheduled_time='10:00', activity_type='journal')
            for i in range(1, 5)
        ]
        rs = compute_recovery_state(items, dt.time(20, 30))
        self.assertEqual(rs['mode'], SHUTDOWN)
        self.assertEqual(rs['day_narrative'], NARR_EVENING_CLOSEOUT)

    def test_foundational_expired_drives_missed_count(self):
        items = [
            _item(
                id=1, scheduled_time='10:30', activity_type='service',
                is_foundational=True,
            ),
        ]
        rs = compute_recovery_state(items, dt.time(14, 0))
        self.assertEqual(rs['missed_foundational_count'], 1)
        self.assertEqual(rs['expired_count'], 1)

    def test_completed_items_dont_count(self):
        items = [
            _item(
                id=1, scheduled_time='10:30', activity_type='service',
                is_foundational=True,
                completed_today=True, is_actionable=False,
            ),
        ]
        rs = compute_recovery_state(items, dt.time(14, 0))
        self.assertEqual(rs['missed_foundational_count'], 0)
        self.assertEqual(rs['mode'], NORMAL)
