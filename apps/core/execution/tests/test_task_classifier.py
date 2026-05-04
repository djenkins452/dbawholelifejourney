"""Tests for the deterministic task classifier."""

from django.test import SimpleTestCase

from apps.core.execution.task_classifier import (
    FLEXIBLE,
    HARD_EXPIRED,
    SOFT_EXPIRED,
    WINDOWED,
    annotate,
    classify,
)


def _item(**kw):
    base = {
        'source_type': 'task',
        'source_id': 1,
        'title': 'X',
        'domain': 'life',
        'is_actionable': True,
        'completed_today': False,
        'time_status': 'upcoming',
    }
    base.update(kw)
    return base


class TaskClassifierTests(SimpleTestCase):

    def test_event_activity_type_is_hard_expired(self):
        cls, grace, reset = classify(_item(
            source_type='routine_item',
            activity_type='service',
            scheduled_time='10:30',
        ))
        self.assertEqual(cls, HARD_EXPIRED)
        self.assertEqual(grace, 0)
        self.assertFalse(reset)

    def test_meeting_appointment_class_event_all_hard_expired(self):
        for at in ('event', 'appointment', 'meeting', 'class'):
            cls, _, _ = classify(_item(
                source_type='routine_item', activity_type=at,
                scheduled_time='09:00',
            ))
            self.assertEqual(cls, HARD_EXPIRED, f"activity_type={at}")

    def test_nutrition_anchor_is_windowed(self):
        cls, grace, reset = classify(_item(
            source_type='routine_item',
            activity_type='nutrition_anchor',
            scheduled_time='06:45',
        ))
        self.assertEqual(cls, WINDOWED)
        self.assertEqual(grace, 90)
        self.assertFalse(reset)

    def test_critical_medication_dose_is_windowed_60(self):
        cls, grace, _ = classify(_item(
            source_type='medication_dose',
            priority='critical',
            scheduled_time='08:00',
        ))
        self.assertEqual(cls, WINDOWED)
        self.assertEqual(grace, 60)

    def test_optimization_supplement_is_windowed_120(self):
        cls, grace, _ = classify(_item(
            source_type='supplement_dose',
            priority='optimization',
            scheduled_time='18:00',
        ))
        self.assertEqual(cls, WINDOWED)
        self.assertEqual(grace, 120)

    def test_hygiene_activity_is_soft_expired_reset(self):
        cls, _, reset = classify(_item(
            source_type='routine_item',
            activity_type='hygiene',
            scheduled_time='07:00',
        ))
        self.assertEqual(cls, SOFT_EXPIRED)
        self.assertTrue(reset)

    def test_faith_pause_is_reset(self):
        # 'faith' activity_type marks brief spiritual pause as reset.
        _, _, reset = classify(_item(
            source_type='routine_item', activity_type='faith',
        ))
        self.assertTrue(reset)

    def test_workout_is_soft_expired_not_reset(self):
        cls, _, reset = classify(_item(
            source_type='routine_item', activity_type='workout',
        ))
        self.assertEqual(cls, SOFT_EXPIRED)
        self.assertFalse(reset)

    def test_unscheduled_task_is_flexible(self):
        cls, _, _ = classify(_item(
            source_type='task', scheduled_time=None,
        ))
        self.assertEqual(cls, FLEXIBLE)

    def test_scheduled_task_is_soft_expired(self):
        cls, _, _ = classify(_item(
            source_type='task', scheduled_time='14:00',
        ))
        self.assertEqual(cls, SOFT_EXPIRED)

    def test_routine_without_activity_type_is_soft_expired_not_reset(self):
        cls, _, reset = classify(_item(
            source_type='routine_item',
            activity_type=None,
            scheduled_time='09:00',
        ))
        self.assertEqual(cls, SOFT_EXPIRED)
        self.assertFalse(reset)

    def test_unknown_source_type_is_flexible(self):
        cls, _, _ = classify(_item(source_type='mystery'))
        self.assertEqual(cls, FLEXIBLE)

    def test_annotate_writes_fields_in_place(self):
        item = _item(
            source_type='routine_item', activity_type='service',
            scheduled_time='10:30',
        )
        annotate(item)
        self.assertEqual(item['task_class'], HARD_EXPIRED)
        self.assertEqual(item['recovery_grace_minutes'], 0)
        self.assertFalse(item['is_reset_action'])

    def test_annotate_is_idempotent(self):
        item = _item(
            source_type='medication_dose',
            priority='critical', scheduled_time='08:00',
        )
        annotate(item)
        annotate(item)
        self.assertEqual(item['task_class'], WINDOWED)
        self.assertEqual(item['recovery_grace_minutes'], 60)

    def test_no_title_matching_for_reset(self):
        # A routine titled "Shower" without activity_type='hygiene'
        # must NOT be classified as a reset. Reset comes from
        # activity_type only — never from titles.
        _, _, reset = classify(_item(
            source_type='routine_item', title='Shower',
            activity_type=None,
        ))
        self.assertFalse(reset)
