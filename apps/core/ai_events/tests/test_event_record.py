# ==============================================================================
# File: apps/core/ai_events/tests/test_event_record.py
# Project: Whole Life Journey
# Description: Tests for EventRecord dataclass
# ==============================================================================

from datetime import datetime

from django.test import TestCase
from django.utils import timezone

from apps.core.ai_events.event_record import EventRecord


class EventRecordTest(TestCase):
    """Test EventRecord creation and validation."""

    def test_create_basic_event(self):
        now = timezone.now()
        event = EventRecord(
            domain='medication',
            event_type='dose_missed',
            timestamp=now,
            label='Lantus SoloStar — 9:00 AM',
            status='missed',
        )
        self.assertEqual(event.domain, 'medication')
        self.assertEqual(event.event_type, 'dose_missed')
        self.assertEqual(event.status, 'missed')
        self.assertEqual(event.label, 'Lantus SoloStar — 9:00 AM')

    def test_create_with_detail(self):
        now = timezone.now()
        event = EventRecord(
            domain='medication',
            event_type='dose_taken',
            timestamp=now,
            label='Metformin — 12:00 PM',
            status='taken',
            detail={'medicine_name': 'Metformin', 'dose': '500mg'},
            source_model='MedicineLog',
            source_id=42,
        )
        self.assertEqual(event.detail['medicine_name'], 'Metformin')
        self.assertEqual(event.source_model, 'MedicineLog')
        self.assertEqual(event.source_id, 42)

    def test_frozen_immutable(self):
        """EventRecord should be frozen (immutable)."""
        now = timezone.now()
        event = EventRecord(
            domain='medication',
            event_type='dose_missed',
            timestamp=now,
            label='Test',
            status='missed',
        )
        with self.assertRaises(AttributeError):
            event.status = 'taken'

    def test_missing_domain_raises(self):
        now = timezone.now()
        with self.assertRaises(ValueError):
            EventRecord(
                domain='',
                event_type='dose_missed',
                timestamp=now,
                label='Test',
                status='missed',
            )

    def test_missing_status_raises(self):
        now = timezone.now()
        with self.assertRaises(ValueError):
            EventRecord(
                domain='medication',
                event_type='dose_missed',
                timestamp=now,
                label='Test',
                status='',
            )

    def test_missing_label_raises(self):
        now = timezone.now()
        with self.assertRaises(ValueError):
            EventRecord(
                domain='medication',
                event_type='dose_missed',
                timestamp=now,
                label='',
                status='missed',
            )

    def test_default_detail_is_empty_dict(self):
        now = timezone.now()
        event = EventRecord(
            domain='workout',
            event_type='workout_completed',
            timestamp=now,
            label='Workout (45 min)',
            status='completed',
        )
        self.assertEqual(event.detail, {})

    def test_default_source_fields_are_none(self):
        now = timezone.now()
        event = EventRecord(
            domain='workout',
            event_type='workout_completed',
            timestamp=now,
            label='Workout',
            status='completed',
        )
        self.assertIsNone(event.source_model)
        self.assertIsNone(event.source_id)
