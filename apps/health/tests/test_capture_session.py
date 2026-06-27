"""
Guided Capture Session tests (Medication Acquisition V1 completion).

Covers the capture PROFILES, the confidence-driven next-photo suggestion, the
multi-image COMBINED extraction (richer than any single image), confidence
improvement as images accumulate, and that finalizing produces exactly ONE
MedicationScanDraft with NOTHING canonical until confirmation. Vision is mocked —
these tests assert the session/merge/pipeline logic, not the model's OCR.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.health.capture_profiles import (
    CAPTURE_PROFILES,
    get_profile,
    suggested_next_photo,
)
from apps.health.capture_session import analyze_capture, finalize_capture
from apps.health.models import Intake, MedicationScanDraft
from apps.health.tests.test_medicine_adherence import AdherenceTestMixin

CAPTURE_PATH = "apps.health.capture_session._vision"


def _vresult(category="medicine", details=None, label=""):
    items = [{"details": details or {}, "label": label}] if (details or label) else []
    return SimpleNamespace(error=None, top_category=category, confidence=0.8, items=items)


def _mock_vision(results):
    """A vision_service stand-in whose analyze_image yields one result per image."""
    m = MagicMock()
    m.analyze_image.side_effect = results
    return m


class CaptureProfileTest(TestCase):
    def test_all_four_profiles_present(self):
        for key in ("prescription", "supplement", "otc", "injection"):
            prof = get_profile(key)
            self.assertIsNotNone(prof, f"missing profile {key}")
            self.assertTrue(prof["steps"])
            # Every step has user-facing guidance and a "why".
            for step in prof["steps"]:
                self.assertTrue(step["instruction"])
                self.assertTrue(step["why"])

    def test_suggestion_maps_missing_fields_to_a_photo(self):
        self.assertEqual(suggested_next_photo(["name"]), "a clear photo of the front label")
        self.assertEqual(suggested_next_photo(["rx_number"]), "a photo of the pharmacy label")
        self.assertEqual(suggested_next_photo(["serving_size"]),
                         "a photo of the Supplement Facts panel")
        self.assertIsNone(suggested_next_photo([]))


class CaptureCombinedExtractionTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user(email="cap@test.com")

    def test_combined_extraction_is_richer_than_single_image(self):
        # Front names it; pharmacy label adds dose + Rx + prescriber.
        results = [
            _vresult(details={"name": "Metformin"}),
            _vresult(details={"dosage": "500mg", "rx_number": "RX123",
                              "prescriber": "Dr. Smith"}),
        ]
        with patch(CAPTURE_PATH, return_value=_mock_vision(results)):
            draft = finalize_capture(self.user, ["img1", "img2"],
                                     intake_type="medication")
        self.assertIsNotNone(draft)
        ev = draft.extracted_values
        self.assertEqual(ev["name"], "Metformin")
        self.assertEqual(ev["dose"], "500mg")
        self.assertEqual(ev["rx_number"], "RX123")
        self.assertEqual(ev["provider"], "Dr. Smith")

    def test_confidence_improves_with_more_images(self):
        one = [_vresult(details={"name": "Lipitor"})]
        with patch(CAPTURE_PATH, return_value=_mock_vision(one)):
            r1 = analyze_capture(self.user, ["img1"], intake_type="medication")
        two = [
            _vresult(details={"name": "Lipitor"}),
            _vresult(details={"dosage": "20mg", "directions": "Take one daily",
                              "rx_number": "RX9"}),
        ]
        with patch(CAPTURE_PATH, return_value=_mock_vision(two)):
            r2 = analyze_capture(self.user, ["img1", "img2"], intake_type="medication")
        self.assertTrue(r1["ok"])
        self.assertTrue(r2["ok"])
        self.assertGreater(r2["confidence"], r1["confidence"])

    def test_analyze_makes_no_draft_and_nothing_canonical(self):
        results = [_vresult(details={"name": "Metformin", "dosage": "500mg"})]
        with patch(CAPTURE_PATH, return_value=_mock_vision(results)):
            r = analyze_capture(self.user, ["img1"], intake_type="medication")
        self.assertTrue(r["ok"])
        self.assertEqual(MedicationScanDraft.objects.filter(user=self.user).count(), 0)
        self.assertEqual(Intake.objects.filter(user=self.user).count(), 0)

    def test_finalize_creates_one_draft_nothing_canonical(self):
        results = [_vresult(details={"name": "Metformin", "dosage": "500mg"})]
        with patch(CAPTURE_PATH, return_value=_mock_vision(results)):
            draft = finalize_capture(self.user, ["img1"], intake_type="medication")
        self.assertIsNotNone(draft)
        # Exactly one draft, and NO canonical Intake yet (confirmation pending).
        self.assertEqual(MedicationScanDraft.objects.filter(user=self.user).count(), 1)
        self.assertFalse(Intake.objects.filter(user=self.user).exists())
        self.assertEqual(draft.source, "bottle_image")

    def test_skipping_optional_still_finalizes(self):
        # Only the two required photos (front + supplement facts) — directions skipped.
        results = [
            _vresult(category="supplement", details={"name": "Vitamin D"}),
            _vresult(category="supplement", details={"serving_size": "1 softgel",
                                                     "active_ingredients": "Vit D3 2000 IU"}),
        ]
        with patch(CAPTURE_PATH, return_value=_mock_vision(results)):
            draft = finalize_capture(self.user, ["img1", "img2"],
                                     intake_type="supplement")
        self.assertIsNotNone(draft)
        self.assertEqual(draft.intake_type, Intake.INTAKE_TYPE_SUPPLEMENT)

    def test_unreadable_photos_make_no_draft(self):
        results = [_vresult(details={})]  # nothing usable
        with patch(CAPTURE_PATH, return_value=_mock_vision(results)):
            draft = finalize_capture(self.user, ["img1"], intake_type="medication")
        self.assertIsNone(draft)
        self.assertEqual(MedicationScanDraft.objects.filter(user=self.user).count(), 0)


class CaptureViewTest(AdherenceTestMixin, TestCase):
    def setUp(self):
        self.client = Client()
        self.user = self.create_user(email="capview@test.com")
        self.client.force_login(self.user)

    def _grant_consent(self):
        from apps.scan.models import ScanConsent
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.save()
        ScanConsent.objects.create(
            user=self.user, consent_version="1.0", consented_at=timezone.now())

    def test_capture_page_renders_profile_picker(self):
        self._grant_consent()
        resp = self.client.get(reverse("health:medication_capture"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "What are you capturing?")
        self.assertContains(resp, "Prescription bottle")
        self.assertContains(resp, "Supplement")

    def test_capture_page_gated_without_consent(self):
        resp = self.client.get(reverse("health:medication_capture"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "needs AI")
        self.assertNotContains(resp, "What are you capturing?")

    def test_finalize_requires_consent(self):
        # No consent → 403 with a consent URL (no draft).
        resp = self.client.post(
            reverse("health:medication_capture_finish"),
            data='{"images": ["img1"], "intake_type": "medication"}',
            content_type="application/json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"], "consent_required")
        self.assertEqual(MedicationScanDraft.objects.filter(user=self.user).count(), 0)

    def test_finalize_returns_review_url(self):
        self._grant_consent()
        results = [_vresult(details={"name": "Metformin", "dosage": "500mg"})]
        with patch(CAPTURE_PATH, return_value=_mock_vision(results)):
            resp = self.client.post(
                reverse("health:medication_capture_finish"),
                data='{"images": ["img1", "img2"], "intake_type": "medication"}',
                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("/review/", resp.json()["review_url"])
        self.assertEqual(MedicationScanDraft.objects.filter(user=self.user).count(), 1)

    def test_analyze_returns_confidence_no_draft(self):
        self._grant_consent()
        results = [_vresult(details={"name": "Metformin", "dosage": "500mg"})]
        with patch(CAPTURE_PATH, return_value=_mock_vision(results)):
            resp = self.client.post(
                reverse("health:medication_capture_analyze"),
                data='{"images": ["img1"], "intake_type": "medication"}',
                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertIsNotNone(body["confidence_pct"])
        self.assertEqual(MedicationScanDraft.objects.filter(user=self.user).count(), 0)

    def test_finalize_no_images_is_rejected(self):
        self._grant_consent()
        resp = self.client.post(
            reverse("health:medication_capture_finish"),
            data='{"images": [], "intake_type": "medication"}',
            content_type="application/json")
        self.assertEqual(resp.status_code, 400)
