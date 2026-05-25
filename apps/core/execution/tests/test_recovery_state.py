"""Tests for the deterministic recovery-state machine.

Phase 2 contract (recovery redesign, 2026-05-25):
    SOFT_EXPIRED items in LATE_OPEN status must NEVER trigger
    RECOVERY or STABILIZE. Only foundational WINDOWED items in
    AT_RISK / EXPIRED_WINDOWED state may escalate the mode.
"""

import datetime as dt

from django.test import SimpleTestCase

from apps.core.execution.execution_status import annotate_execution_status
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


def _item(now=None, **kw):
    """Build a fully-annotated ExecutionItem for tests.

    The recovery_state machine reads execution_status, so the helper
    annotates both task_class and execution_status before returning.
    """
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
    annotate(base)
    annotate_execution_status(base, now or dt.time(12, 0))
    return base


class RecoveryStateTests(SimpleTestCase):

    def test_morning_on_track_is_normal(self):
        now = dt.time(9, 0)
        items = [_item(
            now=now,
            id=1, scheduled_time='09:30', time_status='upcoming',
            activity_type='workout',
        )]
        rs = compute_recovery_state(items, now)
        self.assertEqual(rs['mode'], NORMAL)
        self.assertEqual(rs['day_narrative'], NARR_ON_TRACK)

    def test_normal_with_overdue_recoverable_is_behind_recoverable(self):
        now = dt.time(11, 0)
        items = [
            _item(now=now, id=1, scheduled_time='09:30', activity_type='workout'),
        ]
        # 11 AM, before the noon recovery threshold, soft_expired
        # (workout) is still recoverable.
        rs = compute_recovery_state(items, now)
        self.assertEqual(rs['mode'], NORMAL)
        self.assertEqual(rs['day_narrative'], NARR_BEHIND_RECOVERABLE)

    def test_late_soft_expired_items_do_not_trigger_recovery_after_noon(self):
        """Phase 2 contract: SOFT_EXPIRED LATE_OPEN items never escalate
        the mode to RECOVERY.

        Previously a delayed workout + journal at 1 PM flipped the day
        into RECOVERY mode and triggered "rebuild the day forward"
        narration. The new rule is: only foundational WINDOWED items in
        AT_RISK / EXPIRED_WINDOWED state escalate. Late workout and
        journal are LATE_OPEN — Beth must treat them as still planned
        today, not as a schedule failure.
        """
        now = dt.time(13, 0)
        items = [
            _item(now=now, id=1, scheduled_time='09:30', activity_type='workout'),
            _item(now=now, id=2, scheduled_time='10:00', activity_type='journal'),
        ]
        rs = compute_recovery_state(items, now)
        self.assertEqual(
            rs['mode'], NORMAL,
            "Late SOFT_EXPIRED items must NOT trigger RECOVERY",
        )
        self.assertEqual(rs['escalation_overdue_count'], 0)

    def test_foundational_windowed_at_risk_triggers_recovery_after_noon(self):
        """Phase 2 contract: foundational WINDOWED items in AT_RISK
        (past scheduled, inside grace) DO escalate the mode after noon
        when the threshold is met. Safety preserved for medications.
        """
        now = dt.time(13, 0)
        # Two critical (foundational) medication doses past their
        # scheduled time but still inside grace -> AT_RISK.
        items = [
            _item(
                now=now,
                id=1, scheduled_time='12:30', time_status='overdue',
                source_type='medication_dose', intake_type='medication',
                priority='critical', is_foundational=True,
            ),
            _item(
                now=now,
                id=2, scheduled_time='12:45', time_status='overdue',
                source_type='medication_dose', intake_type='medication',
                priority='critical', is_foundational=True,
            ),
        ]
        rs = compute_recovery_state(items, now)
        self.assertEqual(rs['mode'], RECOVERY)
        self.assertEqual(rs['day_narrative'], NARR_DAY_LOST_SALVAGE)
        self.assertGreaterEqual(rs['escalation_overdue_count'], 2)

    def test_stabilize_when_foundational_missed_and_reset_available(self):
        now = dt.time(11, 30)
        items = [
            # Missed foundational church (HARD_EXPIRED, not recoverable)
            _item(
                now=now,
                id=1, scheduled_time='10:30', activity_type='service',
                is_foundational=True,
            ),
            # Available reset action — shower (hygiene = reset)
            _item(
                now=now,
                id=2, scheduled_time='07:00', activity_type='hygiene',
            ),
        ]
        # 11:30 AM — before noon recovery threshold
        rs = compute_recovery_state(items, now)
        self.assertEqual(rs['mode'], STABILIZE)
        self.assertEqual(rs['day_narrative'], NARR_BEHIND_RESET_REQUIRED)
        self.assertTrue(rs['reset_action_available'])

    def test_shutdown_late_with_multiple_overdue(self):
        now = dt.time(20, 30)
        items = [
            _item(now=now, id=i, scheduled_time='10:00', activity_type='journal')
            for i in range(1, 5)
        ]
        rs = compute_recovery_state(items, now)
        self.assertEqual(rs['mode'], SHUTDOWN)
        self.assertEqual(rs['day_narrative'], NARR_EVENING_CLOSEOUT)

    def test_foundational_expired_drives_missed_count(self):
        now = dt.time(14, 0)
        items = [
            _item(
                now=now,
                id=1, scheduled_time='10:30', activity_type='service',
                is_foundational=True,
            ),
        ]
        rs = compute_recovery_state(items, now)
        self.assertEqual(rs['missed_foundational_count'], 1)
        self.assertEqual(rs['expired_count'], 1)

    def test_completed_items_dont_count(self):
        now = dt.time(14, 0)
        items = [
            _item(
                now=now,
                id=1, scheduled_time='10:30', activity_type='service',
                is_foundational=True,
                completed_today=True, is_actionable=False,
            ),
        ]
        rs = compute_recovery_state(items, now)
        self.assertEqual(rs['missed_foundational_count'], 0)
        self.assertEqual(rs['mode'], NORMAL)
