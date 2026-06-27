"""
Sprint 2A — MedicationEvent ledger tests.

Proves the append-only treatment-history foundation:
  - creating an Intake records exactly one canonical 'started' event,
  - lifecycle changes (pause/resume/complete/refill) each append an event,
  - events are immutable (append-only),
  - Intake remains the canonical current-state projection,
  - the deterministic timeline reads newest-first.
"""

from datetime import date

from django.test import TestCase

from apps.health.medication_events import (
    get_medication_timeline,
    record_medication_change,
)
from apps.health.models import Intake, MedicationEvent

from apps.health.tests.test_medicine_adherence import AdherenceTestMixin


class MedicationEventLedgerTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user(email="medevent@test.com")

    def test_create_intake_records_started_event(self):
        med = self.create_medicine(self.user, name="Lisinopril")
        events = list(med.events.all())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, MedicationEvent.EVENT_STARTED)
        self.assertEqual(events[0].source, MedicationEvent.SOURCE_LIFECYCLE)
        self.assertEqual(events[0].effective_date, med.start_date)

    def test_pause_records_paused_event_with_detail(self):
        med = self.create_medicine(self.user)
        med.pause("Side effects")
        paused = med.events.filter(event_type=MedicationEvent.EVENT_PAUSED).first()
        self.assertIsNotNone(paused)
        self.assertEqual(paused.reason_detail, "Side effects")
        # Reason is UNKNOWN by default — we never assume a clinical reason.
        self.assertEqual(paused.reason, MedicationEvent.REASON_UNKNOWN)
        # Intake remains the canonical current state.
        med.refresh_from_db()
        self.assertEqual(med.intake_status, Intake.STATUS_PAUSED)

    def test_resume_records_resumed_event(self):
        med = self.create_medicine(self.user)
        med.pause("x")
        med.resume()
        self.assertTrue(
            med.events.filter(event_type=MedicationEvent.EVENT_RESUMED).exists()
        )
        med.refresh_from_db()
        self.assertEqual(med.intake_status, Intake.STATUS_ACTIVE)

    def test_complete_records_discontinued_event(self):
        med = self.create_medicine(self.user)
        med.complete()
        ev = med.events.filter(event_type=MedicationEvent.EVENT_DISCONTINUED).first()
        self.assertIsNotNone(ev)
        med.refresh_from_db()
        self.assertEqual(med.intake_status, Intake.STATUS_COMPLETED)

    def test_request_refill_records_refill_event(self):
        med = self.create_medicine(self.user)
        med.request_refill()
        self.assertTrue(
            med.events.filter(event_type=MedicationEvent.EVENT_REFILL).exists()
        )

    def test_event_is_append_only(self):
        med = self.create_medicine(self.user)
        ev = med.events.first()
        ev.reason_detail = "tampered"
        with self.assertRaises(ValueError):
            ev.save()

    def test_record_medication_change_defaults(self):
        med = self.create_medicine(self.user)
        ev = record_medication_change(med, MedicationEvent.EVENT_DOSE_CHANGED,
                                      previous_value={"dose": "10mg"},
                                      new_value={"dose": "20mg"})
        self.assertEqual(ev.reason, MedicationEvent.REASON_UNKNOWN)
        self.assertEqual(ev.source, MedicationEvent.SOURCE_LIFECYCLE)
        self.assertEqual(ev.user_id, self.user.id)

    def test_timeline_is_newest_first(self):
        med = self.create_medicine(self.user)  # started
        med.pause("a")                         # paused
        med.resume()                           # resumed
        timeline = get_medication_timeline(med)
        self.assertEqual(len(timeline), 3)
        # Meta.ordering = -effective_date, -created_at → most recent first.
        self.assertEqual(timeline[0].event_type, MedicationEvent.EVENT_RESUMED)
        self.assertEqual(timeline[-1].event_type, MedicationEvent.EVENT_STARTED)

    def test_history_failure_never_blocks_lifecycle(self):
        """If ledger writing fails, the lifecycle action still succeeds."""
        from unittest.mock import patch
        med = self.create_medicine(self.user)
        with patch(
            "apps.health.medication_events.record_medication_change",
            side_effect=RuntimeError("boom"),
        ):
            med.pause("x")  # must not raise
        med.refresh_from_db()
        self.assertEqual(med.intake_status, Intake.STATUS_PAUSED)
