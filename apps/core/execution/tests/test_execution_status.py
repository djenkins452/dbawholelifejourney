"""Tests for the deterministic execution_status derivation (Phase 1).

execution_status is the single source of truth for "what state is this
item in *right now*?" Every consumer reads from it instead of
re-deriving lateness independently.
"""

import datetime as dt

from django.test import SimpleTestCase

from apps.core.execution.execution_status import (
    AT_RISK,
    EXPIRED_HARD,
    EXPIRED_WINDOWED,
    LATE_OPEN,
    ON_TIME,
    SKIPPED,
    annotate_execution_status,
    compute_execution_status,
    worst_status,
)
from apps.core.execution.task_classifier import (
    FLEXIBLE,
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


class ExecutionStatusDerivationTests(SimpleTestCase):

    # ── ON_TIME ────────────────────────────────────────────────────
    def test_unscheduled_flexible_item_is_on_time(self):
        item = _item(scheduled_time=None, activity_type=None)
        self.assertEqual(
            compute_execution_status(item, dt.time(14, 0)), ON_TIME,
        )

    def test_item_before_scheduled_is_on_time(self):
        item = _item(scheduled_time='15:00', activity_type='workout')
        self.assertEqual(
            compute_execution_status(item, dt.time(14, 0)), ON_TIME,
        )

    # ── LATE_OPEN (SOFT_EXPIRED past scheduled) ────────────────────
    def test_late_workout_is_late_open(self):
        # 6:15 AM workout, 11:13 AM current — the canonical scenario.
        item = _item(scheduled_time='06:15', activity_type='workout')
        self.assertEqual(
            compute_execution_status(item, dt.time(11, 13)), LATE_OPEN,
        )

    def test_late_journal_is_late_open(self):
        item = _item(scheduled_time='07:00', activity_type='journal')
        self.assertEqual(
            compute_execution_status(item, dt.time(14, 0)), LATE_OPEN,
        )

    def test_late_bible_reading_is_late_open(self):
        item = _item(scheduled_time='07:00', activity_type='bible')
        self.assertEqual(
            compute_execution_status(item, dt.time(14, 0)), LATE_OPEN,
        )

    def test_late_shower_is_late_open(self):
        # hygiene = reset_action AND SOFT_EXPIRED. Status is LATE_OPEN
        # — the reset flag is separate from execution status.
        item = _item(scheduled_time='07:00', activity_type='hygiene')
        self.assertEqual(
            compute_execution_status(item, dt.time(11, 13)), LATE_OPEN,
        )

    # ── AT_RISK (WINDOWED inside grace) ────────────────────────────
    def test_windowed_inside_grace_is_at_risk(self):
        # nutrition_anchor = WINDOWED, default grace 90 min.
        # Scheduled 07:00, current 07:45 → inside grace.
        item = _item(
            scheduled_time='07:00', activity_type='nutrition_anchor',
        )
        self.assertEqual(
            compute_execution_status(item, dt.time(7, 45)), AT_RISK,
        )

    def test_medication_inside_grace_is_at_risk(self):
        # Critical medication: 60-min grace per task_classifier.
        item = _item(
            scheduled_time='13:00',
            source_type='medication_dose',
            intake_type='medication',
            priority='critical',
            is_foundational=True,
        )
        self.assertEqual(
            compute_execution_status(item, dt.time(13, 30)), AT_RISK,
        )

    # ── EXPIRED_WINDOWED ───────────────────────────────────────────
    def test_windowed_past_grace_is_expired_windowed(self):
        # nutrition_anchor at 06:45, current 09:00 → grace cutoff is
        # at 08:15 OR next_anchor_block_start (whichever is earlier).
        item = _item(
            scheduled_time='06:45', activity_type='nutrition_anchor',
        )
        self.assertEqual(
            compute_execution_status(item, dt.time(11, 0)),
            EXPIRED_WINDOWED,
        )

    # ── EXPIRED_HARD ───────────────────────────────────────────────
    def test_hard_expired_past_scheduled_is_expired_hard(self):
        # Missed church service.
        item = _item(scheduled_time='10:30', activity_type='service')
        self.assertEqual(
            compute_execution_status(item, dt.time(14, 0)), EXPIRED_HARD,
        )

    def test_missed_meeting_is_expired_hard(self):
        item = _item(scheduled_time='09:00', activity_type='meeting')
        self.assertEqual(
            compute_execution_status(item, dt.time(10, 0)), EXPIRED_HARD,
        )

    # ── SKIPPED ────────────────────────────────────────────────────
    def test_explicit_skip_overrides_everything(self):
        item = _item(
            scheduled_time='06:15', activity_type='workout',
            completion_status='skipped',
        )
        self.assertEqual(
            compute_execution_status(item, dt.time(11, 13)), SKIPPED,
        )

    # ── annotate_execution_status mutator ──────────────────────────
    def test_annotate_writes_field_in_place(self):
        item = _item(scheduled_time='06:15', activity_type='workout')
        out = annotate_execution_status(item, dt.time(11, 13))
        self.assertIs(out, item)
        self.assertEqual(item['execution_status'], LATE_OPEN)

    def test_annotate_is_idempotent(self):
        item = _item(scheduled_time='06:15', activity_type='workout')
        annotate_execution_status(item, dt.time(11, 13))
        first = item['execution_status']
        annotate_execution_status(item, dt.time(11, 13))
        self.assertEqual(item['execution_status'], first)


class WorstStatusAggregationTests(SimpleTestCase):

    def test_expired_hard_beats_everything(self):
        self.assertEqual(
            worst_status(LATE_OPEN, AT_RISK, EXPIRED_HARD, ON_TIME),
            EXPIRED_HARD,
        )

    def test_expired_windowed_beats_at_risk(self):
        self.assertEqual(
            worst_status(AT_RISK, EXPIRED_WINDOWED), EXPIRED_WINDOWED,
        )

    def test_at_risk_beats_late_open(self):
        self.assertEqual(
            worst_status(LATE_OPEN, AT_RISK), AT_RISK,
        )

    def test_late_open_beats_on_time(self):
        self.assertEqual(
            worst_status(ON_TIME, LATE_OPEN), LATE_OPEN,
        )

    def test_none_treated_as_least_severe(self):
        self.assertEqual(
            worst_status(None, ON_TIME), ON_TIME,
        )
