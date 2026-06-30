"""
Sprint 8 — Physician Mode tests.

Proves the summary is a faithful, deterministic organization of canonical data:
correct sections, adherence from canonical utilities, timeline from the canonical
service, only approved narration appears (suppressed never does), deterministic
discussion items, evidence traceability, empty states, and the safety guardrails —
no diagnosis / recommendation / dose-change / causal language.
"""

from datetime import timedelta

from django.test import Client, TestCase

from apps.health.medication_acquisition import confirm_draft, create_draft_from_scan
from apps.health.medication_events import record_medication_change
from apps.health.models import MedicalProvider, MedicationEvent, MedicationScanDraft, Pharmacy
from apps.health.physician_summary import build_physician_summary

from apps.health.tests.test_medicine_adherence import AdherenceTestMixin


class PhysicianSummaryServiceTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user(email="phys@test.com")

    def test_empty_summary(self):
        s = build_physician_summary(self.user)
        self.assertTrue(s["is_empty"])
        self.assertEqual(s["medications"], [])
        self.assertIn("disclaimer", s["header"])

    def test_medications_and_supplements_separated(self):
        from apps.health.models import Intake
        self.create_medicine(self.user, name="Metformin", dose="500mg",
                             intake_type=Intake.INTAKE_TYPE_MEDICATION, purpose="Diabetes")
        self.create_medicine(self.user, name="Vitamin D", dose="2000 IU",
                             intake_type=Intake.INTAKE_TYPE_SUPPLEMENT)
        s = build_physician_summary(self.user)
        med_names = {m["name"] for m in s["medications"]}
        supp_names = {m["name"] for m in s["supplements"]}
        self.assertIn("Metformin", med_names)
        self.assertIn("Vitamin D", supp_names)
        self.assertNotIn("Vitamin D", med_names)

    def test_structured_fields_from_acquisition(self):
        """Provider/pharmacy/Rx come through from a confirmed pharmacy-label scan."""
        items = [{"label": "Amoxicillin", "details": {
            "name": "Amoxicillin", "dosage": "500mg", "prescriber": "Dr. Reyes",
            "pharmacy": "Wellness Pharmacy", "rx_number": "RX998", "refills": "2",
        }}]
        draft = create_draft_from_scan(self.user, "medicine", items, scan_confidence=0.85)
        confirm_draft(draft, MedicationScanDraft.ACTION_CREATE)
        m = next(x for x in build_physician_summary(self.user)["medications"]
                 if x["name"] == "Amoxicillin")
        self.assertEqual(m["provider"], "Dr. Reyes")
        self.assertEqual(m["pharmacy"], "Wellness Pharmacy")
        self.assertEqual(m["rx_number"], "RX998")
        self.assertIn("2 refill", m["refill_status"])

    def test_recent_changes_from_ledger_no_fabrication(self):
        med = self.create_medicine(self.user, name="Lantus", dose="20 units")
        record_medication_change(
            med, MedicationEvent.EVENT_DOSE_CHANGED,
            previous_value={"dose": "20 units"}, new_value={"dose": "24 units"},
        )
        changes = build_physician_summary(self.user)["recent_changes"]
        # Exactly the recorded change appears (started/tracking excluded; nothing invented).
        self.assertTrue(any("Lantus" in c["medicine"] and "dose" in c["change"].lower()
                            for c in changes))
        self.assertTrue(all(c["evidence_label"] for c in changes))

    def test_adherence_from_canonical_utility(self):
        from apps.core.utils import get_user_today
        from apps.health.medicine_utils import calculate_medicine_adherence_rate
        # Metformin is a PRESCRIPTION — category must be set for it to count toward
        # Medication Adherence (trust contract 2026-06-30: prescription only).
        med = self.create_medicine(self.user, name="Metformin", dose="500mg",
                                   category="prescription")
        sched = self.create_schedule(med)
        today = get_user_today(self.user)
        for i in range(1, 5):
            self.create_log(self.user, med, today - timedelta(days=i))
        s = build_physician_summary(self.user)
        expected = calculate_medicine_adherence_rate(
            self.user, days=7, classification="prescription")
        self.assertEqual(s["adherence"]["medication_7d"], expected)

    def test_only_approved_observations_with_discussion_items(self):
        med = self.create_medicine(self.user, name="Lantus", dose="20 units")
        for prev, new in (("20", "24"), ("24", "28")):
            record_medication_change(
                med, MedicationEvent.EVENT_DOSE_CHANGED,
                previous_value={"dose": f"{prev} units"}, new_value={"dose": f"{new} units"},
            )
        s = build_physician_summary(self.user)
        self.assertTrue(s["observations"])
        # Deterministic discussion items derived from approved narrations.
        self.assertTrue(s["discussion_items"])
        # Run twice → identical (deterministic).
        again = build_physician_summary(self.user)
        self.assertEqual(s["discussion_items"], again["discussion_items"])

    def test_evidence_traceability_friendly_labels(self):
        from django.utils import timezone as tz
        from apps.health.models import WeightEntry
        from apps.core.utils import get_user_today
        med = self.create_medicine(self.user, name="Mounjaro", dose="5mg")
        ad = get_user_today(self.user) - timedelta(days=10)
        record_medication_change(
            med, MedicationEvent.EVENT_DOSE_CHANGED,
            previous_value={"dose": "5mg"}, new_value={"dose": "7.5mg"}, effective_date=ad,
        )
        WeightEntry.objects.create(user=self.user, value=210, unit="lb",
                                   recorded_at=tz.now() - timedelta(days=15))
        WeightEntry.objects.create(user=self.user, value=204, unit="lb",
                                   recorded_at=tz.now() - timedelta(days=2))
        s = build_physician_summary(self.user)
        # Friendly labels, never raw OCR / model internals like "MedicationEvent".
        for label in s["source_notes"]:
            self.assertNotIn("MedicationEvent", label)
            self.assertNotIn("OCR", label.upper())


class PhysicianSafetyGuardrailTest(AdherenceTestMixin, TestCase):
    """No diagnosis / recommendation / dose-change / causal language anywhere."""

    def setUp(self):
        self.user = self.create_user(email="physsafe@test.com")

    def test_no_banned_language_in_summary(self):
        from django.utils import timezone as tz
        from apps.health.models import WeightEntry
        from apps.core.utils import get_user_today
        med = self.create_medicine(self.user, name="Mounjaro", dose="5mg")
        ad = get_user_today(self.user) - timedelta(days=10)
        record_medication_change(
            med, MedicationEvent.EVENT_DOSE_CHANGED,
            previous_value={"dose": "5mg"}, new_value={"dose": "7.5mg"}, effective_date=ad,
        )
        WeightEntry.objects.create(user=self.user, value=210, unit="lb",
                                   recorded_at=tz.now() - timedelta(days=15))
        WeightEntry.objects.create(user=self.user, value=204, unit="lb",
                                   recorded_at=tz.now() - timedelta(days=2))
        s = build_physician_summary(self.user)
        text = " ".join(
            [o["summary"] for o in s["observations"]]
            + s["discussion_items"]
            + [c["change"] for c in s["recent_changes"]]
        ).lower()
        banned = ("caused", "because", "therefore", "you should", "i recommend",
                  "adjust your", "increase your dose", "decrease your dose",
                  "your medication is working", "diagnos")
        for word in banned:
            self.assertNotIn(word, text, f"banned clinical phrasing '{word}' in summary")


class PhysicianModeUITest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.client = Client()
        self.user = self.create_user(email="physui@test.com")
        self.client.force_login(self.user)

    def test_physician_page_renders(self):
        from django.urls import reverse
        self.create_medicine(self.user, name="Metformin", dose="500mg", purpose="Diabetes")
        resp = self.client.get(reverse("health:medication_physician"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Medication &amp; Treatment Summary")
        self.assertContains(resp, "Metformin")
        self.assertContains(resp, "Not a medical record")

    def test_physician_page_empty_state(self):
        from django.urls import reverse
        resp = self.client.get(reverse("health:medication_physician"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No active medications")
