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
from apps.health.models import (
    Intake,
    MedicalProvider,
    MedicationEvent,
    Pharmacy,
    Prescription,
)

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


class MedicationMetadataTest(AdherenceTestMixin, TestCase):
    """Sprint 2B — structured treatment metadata (provider/pharmacy/prescription)."""

    def setUp(self):
        self.user = self.create_user(email="medmeta@test.com")

    def test_intake_provider_reuses_medical_provider(self):
        """Provider linkage reuses the existing MedicalProvider model (no new model)."""
        provider = MedicalProvider.objects.create(
            user=self.user, name="Dr. Endo", specialty="endocrinology",
        )
        med = self.create_medicine(self.user, provider=provider)
        med.refresh_from_db()
        self.assertEqual(med.provider, provider)
        self.assertIn(med, provider.intakes.all())

    def test_pharmacy_is_dedicated_model(self):
        """Pharmacy is its own dedicated model (Phase 2 O-8), not a MedicalProvider."""
        pharm = Pharmacy.objects.create(
            user=self.user, name="Corner Pharmacy", phone="555-1234",
        )
        med = self.create_medicine(self.user, pharmacy_ref=pharm)
        med.refresh_from_db()
        self.assertEqual(med.pharmacy_ref, pharm)
        # Free-text fallback field still exists and is independent.
        self.assertTrue(hasattr(med, "pharmacy"))

    def test_prescription_links_intake_provider_pharmacy(self):
        provider = MedicalProvider.objects.create(user=self.user, name="Dr. Rx")
        pharm = Pharmacy.objects.create(user=self.user, name="Rx Mart")
        med = self.create_medicine(self.user)
        rx = Prescription.objects.create(
            user=self.user, intake=med, provider=provider, pharmacy=pharm,
            rx_number="ABC123", refills_authorized=3, refills_remaining=2,
            sig_text="Take 1 tablet by mouth daily",
        )
        self.assertIn(rx, med.prescriptions.all())
        self.assertEqual(rx.provider, provider)
        self.assertEqual(rx.pharmacy, pharm)
        self.assertEqual(rx.refills_remaining, 2)

    def test_monitoring_requirements_field(self):
        med = self.create_medicine(
            self.user, monitoring_requirements="A1c every 3 months",
        )
        med.refresh_from_db()
        self.assertEqual(med.monitoring_requirements, "A1c every 3 months")


class MedicineStateContractTest(AdherenceTestMixin, TestCase):
    """Sprint 2C — build_medicine_state exposes the new canonical treatment section."""

    def setUp(self):
        self.user = self.create_user(email="medstate@test.com")

    def test_treatment_section_present_with_detail_and_changes(self):
        from apps.core.ai_state.state_builder import build_medicine_state

        from apps.core.utils import get_user_today
        provider = MedicalProvider.objects.create(user=self.user, name="Dr. Who")
        med = self.create_medicine(
            self.user, name="Mounjaro", dose="5mg", frequency="weekly",
            purpose="Glucose control", provider=provider,
            monitoring_requirements="A1c q3mo",
            start_date=get_user_today(self.user),  # recent → 'started' is a recent change
        )  # creation → 'started' event (a recent change)

        state = build_medicine_state(self.user)
        contract = state["_contract"]
        self.assertIn("treatment", contract)
        treatment = contract["treatment"]

        # Per-med composed detail (dose/frequency/provider/purpose/monitoring) — no raw models.
        detail = {d["name"]: d for d in treatment["medications_detail"]}
        self.assertIn("Mounjaro", detail)
        self.assertEqual(detail["Mounjaro"]["dose"], "5mg")
        self.assertEqual(detail["Mounjaro"]["frequency"], "Weekly")
        self.assertEqual(detail["Mounjaro"]["provider"], "Dr. Who")
        self.assertEqual(detail["Mounjaro"]["purpose"], "Glucose control")
        self.assertEqual(detail["Mounjaro"]["monitoring"], "A1c q3mo")

        # Recent changes read from the canonical ledger (the 'started' event).
        changes = treatment["recent_changes"]
        self.assertTrue(any(c["medicine"] == "Mounjaro" and c["change"] == "Started" for c in changes))

        # Deterministic treatment summary (verdict-bearing).
        self.assertIn("medication", treatment["treatment_summary"])

    def test_tracking_began_excluded_from_recent_changes(self):
        """The honest backfill marker is not surfaced as a 'recent change'."""
        from apps.core.ai_state.state_builder import build_medicine_state
        from apps.health.medication_events import record_medication_change
        from apps.health.models import MedicationEvent

        med = self.create_medicine(self.user, name="Old Med")
        # Simulate a backfill marker (as the migration would create).
        record_medication_change(
            med, MedicationEvent.EVENT_TRACKING_BEGAN,
            reason=MedicationEvent.REASON_BACKFILL,
            source=MedicationEvent.SOURCE_BACKFILL,
        )
        state = build_medicine_state(self.user)
        changes = state["_contract"]["treatment"]["recent_changes"]
        self.assertFalse(any(c["change"] == "Tracking began" for c in changes))
