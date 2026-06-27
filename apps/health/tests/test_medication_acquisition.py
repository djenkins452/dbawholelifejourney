"""
Sprint 3 — Medication Acquisition pipeline tests.

Covers the permanent acquisition architecture: drafting (bottle/manual/supplement/
injection), the confidence engine (per-field + overall), duplicate detection,
guided-review helpers, and confirmation (create/update/discontinue/replace/ignore)
through the single canonical write path — including MedicationEvent creation, Intake
updates, and the no-duplicate guarantees.
"""

from django.test import TestCase

from apps.health.medication_acquisition import (
    confirm_draft,
    create_draft,
    create_manual_draft,
    detect_duplicates,
)
from apps.health.medication_confidence import (
    compute_field_confidences,
    compute_overall_confidence,
    confidence_band,
    missing_fields,
)
from apps.health.models import Intake, MedicationEvent, MedicationScanDraft

from apps.health.tests.test_medicine_adherence import AdherenceTestMixin


class ConfidenceEngineTest(TestCase):
    def test_manual_fields_are_high_confidence(self):
        fc = compute_field_confidences(
            {"name": "Lantus", "dose": "20u"}, "manual",
            user_edited_fields=["name", "dose"],
        )
        self.assertGreaterEqual(fc["name"], 0.95)
        self.assertGreaterEqual(fc["dose"], 0.95)

    def test_bottle_fields_use_source_default_or_extraction(self):
        fc = compute_field_confidences(
            {"name": "Metformin", "dose": "500mg"}, "bottle_image",
            extraction_confidences={"name": 0.8},
        )
        self.assertEqual(fc["name"], 0.8)        # extraction-provided
        self.assertEqual(fc["dose"], 0.60)       # bottle source default

    def test_absent_field_is_not_low_confidence(self):
        fc = compute_field_confidences({"name": "X", "dose": ""}, "manual")
        self.assertIn("name", fc)
        self.assertNotIn("dose", fc)             # absence ≠ 0.0

    def test_overall_penalizes_missing_critical(self):
        # No name → capped low even if other fields are perfect.
        fc = {"frequency": 0.95, "purpose": 0.95}
        self.assertLessEqual(compute_overall_confidence(fc), 0.30)

    def test_overall_confirmed_is_high(self):
        fc = {"name": 0.6, "dose": 0.6}
        self.assertGreaterEqual(
            compute_overall_confidence(fc, user_confirmed=True), 0.97
        )

    def test_existing_match_boosts(self):
        fc = {"name": 0.7, "dose": 0.7}
        base = compute_overall_confidence(fc)
        boosted = compute_overall_confidence(fc, has_existing_match=True)
        self.assertGreater(boosted, base)

    def test_missing_fields_and_bands(self):
        miss = missing_fields({"name": "X", "dose": "1"}, intake_type="medication")
        self.assertIn("frequency", miss)
        self.assertNotIn("name", miss)
        self.assertEqual(confidence_band(0.9), "high")
        self.assertEqual(confidence_band(0.6), "medium")
        self.assertEqual(confidence_band(0.3), "needs_confirmation")
        self.assertEqual(confidence_band(None), "missing")


class AcquisitionDraftTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user(email="acq@test.com")

    def test_bottle_acquisition_creates_pending_draft(self):
        draft = create_draft(
            self.user, "bottle_image",
            {"name": "Metformin", "dose": "500mg", "frequency": "twice_daily"},
            extraction_confidences={"name": 0.75},
        )
        self.assertEqual(draft.review_status, MedicationScanDraft.REVIEW_PENDING)
        self.assertEqual(draft.source, "bottle_image")
        self.assertIsNotNone(draft.overall_confidence)
        # No canonical write happened yet.
        self.assertFalse(Intake.objects.filter(user=self.user, name="Metformin").exists())
        # Evidence envelope records the acquisition.
        self.assertTrue(any(e.get("source_type") == "acquisition" for e in draft.evidence))

    def test_manual_acquisition_is_high_confidence(self):
        draft = create_manual_draft(
            self.user, {"name": "Vitamin D", "dose": "2000 IU"},
            intake_type=Intake.INTAKE_TYPE_SUPPLEMENT,
        )
        self.assertEqual(draft.source, "manual")
        self.assertGreaterEqual(draft.overall_confidence, 0.9)
        self.assertEqual(draft.intake_type, Intake.INTAKE_TYPE_SUPPLEMENT)

    def test_supplement_acquisition(self):
        draft = create_manual_draft(
            self.user, {"name": "Creatine", "dose": "5g"},
            intake_type=Intake.INTAKE_TYPE_SUPPLEMENT,
        )
        intake = confirm_draft(draft, MedicationScanDraft.ACTION_CREATE)
        self.assertEqual(intake.intake_type, Intake.INTAKE_TYPE_SUPPLEMENT)

    def test_injection_acquisition(self):
        draft = create_manual_draft(
            self.user, {"name": "Lantus", "dose": "20 units", "frequency": "daily"},
        )
        intake = confirm_draft(draft, MedicationScanDraft.ACTION_CREATE)
        self.assertEqual(intake.name, "Lantus")
        self.assertEqual(intake.dose, "20 units")


class DuplicateDetectionTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user(email="dup@test.com")

    def test_exact_duplicate_detected(self):
        self.create_medicine(self.user, name="Metformin", dose="500mg")
        draft = create_manual_draft(self.user, {"name": "Metformin", "dose": "500mg"})
        dups = detect_duplicates(self.user, draft)
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]["match_type"], "exact")

    def test_same_name_different_dose_detected(self):
        self.create_medicine(self.user, name="Lisinopril", dose="10mg")
        draft = create_manual_draft(self.user, {"name": "Lisinopril", "dose": "20mg"})
        dups = detect_duplicates(self.user, draft)
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]["match_type"], "same_name_diff_dose")
        self.assertTrue(dups[0]["dose_differs"])

    def test_no_false_duplicate(self):
        self.create_medicine(self.user, name="Aspirin", dose="81mg")
        draft = create_manual_draft(self.user, {"name": "Ibuprofen", "dose": "200mg"})
        self.assertEqual(detect_duplicates(self.user, draft), [])


class ConfirmationTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user(email="confirm@test.com")

    def test_confirm_create_writes_intake_and_started_event(self):
        draft = create_manual_draft(
            self.user, {"name": "Atorvastatin", "dose": "40mg", "frequency": "daily"},
        )
        intake = confirm_draft(draft, MedicationScanDraft.ACTION_CREATE)
        self.assertIsNotNone(intake.pk)
        self.assertEqual(intake.name, "Atorvastatin")
        # Exactly one canonical Intake (no duplicate).
        self.assertEqual(Intake.objects.filter(user=self.user, name="Atorvastatin").count(), 1)
        # Exactly one 'started' MedicationEvent (no duplicate), via the signal.
        started = intake.events.filter(event_type=MedicationEvent.EVENT_STARTED)
        self.assertEqual(started.count(), 1)
        # Draft is now confirmed + linked + high confidence.
        draft.refresh_from_db()
        self.assertEqual(draft.review_status, MedicationScanDraft.REVIEW_CONFIRMED)
        self.assertEqual(draft.created_intake_id, intake.id)
        self.assertGreaterEqual(draft.overall_confidence, 0.97)

    def test_confirm_update_records_dose_changed_event_no_new_intake(self):
        med = self.create_medicine(self.user, name="Lantus", dose="20 units")
        before = Intake.objects.filter(user=self.user).count()
        draft = create_manual_draft(self.user, {"name": "Lantus", "dose": "24 units"})
        result = confirm_draft(
            draft, MedicationScanDraft.ACTION_UPDATE, target_intake=med,
        )
        # Updated in place — no new Intake created.
        self.assertEqual(result.id, med.id)
        self.assertEqual(Intake.objects.filter(user=self.user).count(), before)
        med.refresh_from_db()
        self.assertEqual(med.dose, "24 units")
        # A dose_changed event was recorded via the single writer.
        self.assertTrue(
            med.events.filter(event_type=MedicationEvent.EVENT_DOSE_CHANGED).exists()
        )

    def test_confirm_discontinue(self):
        med = self.create_medicine(self.user, name="Old Med")
        draft = create_manual_draft(self.user, {"name": "Old Med"})
        confirm_draft(draft, MedicationScanDraft.ACTION_DISCONTINUE, target_intake=med)
        med.refresh_from_db()
        self.assertEqual(med.intake_status, Intake.STATUS_COMPLETED)
        self.assertTrue(
            med.events.filter(event_type=MedicationEvent.EVENT_DISCONTINUED).exists()
        )

    def test_confirm_replace_discontinues_old_creates_new(self):
        old = self.create_medicine(self.user, name="Brand A", dose="10mg")
        draft = create_manual_draft(self.user, {"name": "Brand A", "dose": "10mg"})
        new = confirm_draft(
            draft, MedicationScanDraft.ACTION_REPLACE, target_intake=old,
        )
        old.refresh_from_db()
        self.assertEqual(old.intake_status, Intake.STATUS_COMPLETED)
        self.assertNotEqual(new.id, old.id)
        self.assertEqual(new.intake_status, Intake.STATUS_ACTIVE)

    def test_confirm_ignore_writes_nothing(self):
        before = Intake.objects.filter(user=self.user).count()
        draft = create_manual_draft(self.user, {"name": "Ignore Me"})
        result = confirm_draft(draft, MedicationScanDraft.ACTION_IGNORE)
        self.assertIsNone(result)
        self.assertEqual(Intake.objects.filter(user=self.user).count(), before)
        draft.refresh_from_db()
        self.assertEqual(draft.review_status, MedicationScanDraft.REVIEW_REJECTED)

    def test_edits_applied_before_confirm(self):
        """User edits during review are applied and treated as confirmation."""
        draft = create_draft(
            self.user, "bottle_image", {"name": "Metformn", "dose": "500mg"},
        )
        intake = confirm_draft(
            draft, MedicationScanDraft.ACTION_CREATE,
            edits={"name": "Metformin"},  # user corrected the OCR typo
        )
        self.assertEqual(intake.name, "Metformin")


class AcquisitionStateTest(AdherenceTestMixin, TestCase):
    """Sprint 3I — acquisition confidence is exposed in canonical state."""

    def setUp(self):
        self.user = self.create_user(email="acqstate@test.com")

    def test_state_exposes_pending_and_confirmed_acquisition(self):
        from apps.core.ai_state.state_builder import build_medicine_state

        # One pending draft (awaiting review) + one confirmed into an Intake.
        create_manual_draft(self.user, {"name": "Pending Med", "dose": "1mg"})
        d2 = create_manual_draft(self.user, {"name": "Confirmed Med", "dose": "2mg"})
        confirm_draft(d2, MedicationScanDraft.ACTION_CREATE)

        acq = build_medicine_state(self.user)["_contract"]["acquisition"]
        self.assertEqual(acq["pending_review_count"], 1)
        names = {m["name"]: m for m in acq["medications"]}
        self.assertIn("Confirmed Med", names)
        self.assertGreaterEqual(names["Confirmed Med"]["acquisition_confidence"], 0.97)
        self.assertEqual(names["Confirmed Med"]["source"], "manual")
        self.assertTrue(names["Confirmed Med"]["evidence_summary"])  # composed, not raw OCR


class AcquisitionUIWorkflowTest(AdherenceTestMixin, TestCase):
    """Sprint 3J — the Acquire → Review → Confirm workflow via the views."""

    def setUp(self):
        from django.test import Client
        self.client = Client()
        self.user = self.create_user(email="acqui@test.com")
        self.client.force_login(self.user)

    def test_manual_acquire_creates_draft_and_redirects_to_review(self):
        from django.urls import reverse
        resp = self.client.post(reverse("health:medication_acquire"), {
            "intake_type": "medication", "name": "Metformin", "dose": "500mg",
            "frequency": "twice_daily",
        })
        self.assertEqual(resp.status_code, 302)
        draft = MedicationScanDraft.objects.get(user=self.user)
        self.assertIn(f"/{draft.id}/review/", resp.url)
        self.assertEqual(draft.review_status, MedicationScanDraft.REVIEW_PENDING)
        # Nothing canonical yet.
        self.assertFalse(Intake.objects.filter(user=self.user, name="Metformin").exists())

    def test_review_page_renders_with_confidence(self):
        from django.urls import reverse
        draft = create_manual_draft(self.user, {"name": "Lantus", "dose": "20u"})
        resp = self.client.get(
            reverse("health:medication_review", kwargs={"draft_id": draft.id})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Here's what I found")
        self.assertContains(resp, "Lantus")

    def test_confirm_create_writes_canonical_record(self):
        from django.urls import reverse
        draft = create_manual_draft(self.user, {"name": "Atorvastatin", "dose": "40mg"})
        resp = self.client.post(
            reverse("health:medication_confirm", kwargs={"draft_id": draft.id}),
            {"action": "create", "name": "Atorvastatin", "dose": "40mg"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            Intake.objects.filter(user=self.user, name="Atorvastatin").count(), 1
        )
        draft.refresh_from_db()
        self.assertEqual(draft.review_status, MedicationScanDraft.REVIEW_CONFIRMED)

    def test_review_shows_duplicate_and_update_path(self):
        from django.urls import reverse
        self.create_medicine(self.user, name="Lisinopril", dose="10mg")
        draft = create_manual_draft(self.user, {"name": "Lisinopril", "dose": "20mg"})
        resp = self.client.get(
            reverse("health:medication_review", kwargs={"draft_id": draft.id})
        )
        self.assertContains(resp, "Possible match found")
        # Confirm as update → no duplicate Intake.
        self.client.post(
            reverse("health:medication_confirm", kwargs={"draft_id": draft.id}),
            {"action": "update", "name": "Lisinopril", "dose": "20mg",
             "target_intake_id": Intake.objects.get(user=self.user, name="Lisinopril").id},
        )
        self.assertEqual(Intake.objects.filter(user=self.user, name="Lisinopril").count(), 1)
        med = Intake.objects.get(user=self.user, name="Lisinopril")
        self.assertEqual(med.dose, "20mg")
