"""
Guided Capture — background Vision processing tests.

Vision now runs OFF the request path: a view creates a MedicationCaptureSession and
returns immediately; a Celery worker analyzes the images, updates progress, and
stages ONE MedicationScanDraft via the unchanged pipeline; the UI polls status.

Covers profiles, the background processor (single/multi image, combined extraction,
real ScanItem shape, progress, skip-optional, unreadable), the Celery task
(success/failure/timeout/retry classification), and the async endpoints (start →
202, status polling/resume, retry, cancel) — with NOTHING canonical until
confirmation and NO duplicate drafts. Vision is mocked.
"""

from unittest.mock import MagicMock, patch

from celery.exceptions import SoftTimeLimitExceeded
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.health.capture_profiles import get_profile, suggested_next_photo
from apps.health.capture_session import process_capture_session
from apps.health.models import (
    Intake,
    MedicationCaptureSession,
    MedicationScanDraft,
)
from apps.health.tests.test_medicine_adherence import AdherenceTestMixin
from apps.scan.services.vision import ScanItem, ScanResult

VISION_PATH = "apps.health.capture_session._vision"


def _vresult(category="medicine", details=None, label=""):
    # Real production result shape: items are ScanItem DATACLASSES (not dicts).
    items = ([ScanItem(label=label, details=details or {}, confidence=0.8)]
             if (details or label) else [])
    return ScanResult(request_id="t", top_category=category, confidence=0.8,
                      items=items, safety_notes=[], next_best_actions=[])


def _mock_vision(results):
    m = MagicMock()
    m.analyze_image.side_effect = results
    return m


def _session(user, images, *, profile="prescription", intake_type="medication"):
    return MedicationCaptureSession.objects.create(
        user=user, profile=profile, intake_type=intake_type,
        images=images, images_total=len(images), current_step="Queued")


class CaptureProfileTest(TestCase):
    def test_all_four_profiles_present(self):
        for key in ("prescription", "supplement", "otc", "injection"):
            prof = get_profile(key)
            self.assertIsNotNone(prof, f"missing profile {key}")
            self.assertTrue(prof["steps"])
            for step in prof["steps"]:
                self.assertTrue(step["instruction"])
                self.assertTrue(step["why"])

    def test_suggestion_maps_missing_fields_to_a_photo(self):
        self.assertEqual(suggested_next_photo(["name"]), "a clear photo of the front label")
        self.assertEqual(suggested_next_photo(["rx_number"]), "a photo of the pharmacy label")
        self.assertIsNone(suggested_next_photo([]))


class ProcessCaptureSessionTest(AdherenceTestMixin, TestCase):
    """The background processor — runs in the worker, updates the session."""

    def setUp(self):
        self.user = self.create_user(email="capproc@test.com")

    def test_single_image_session_ready_no_canonical(self):
        sess = _session(self.user, ["img1"])
        with patch(VISION_PATH, return_value=_mock_vision(
                [_vresult(details={"name": "Metformin", "dosage": "500mg"})])):
            draft = process_capture_session(sess)
        sess.refresh_from_db()
        self.assertIsNotNone(draft)
        self.assertEqual(sess.processing_status, MedicationCaptureSession.STATUS_READY)
        self.assertEqual(sess.created_draft_id, draft.id)
        self.assertEqual(sess.images_analyzed, 1)
        self.assertEqual(sess.images, [])  # cleared on success (no retention)
        self.assertFalse(Intake.objects.filter(user=self.user).exists())

    def test_multi_image_combined_extraction_richer(self):
        sess = _session(self.user, ["a", "b"])
        results = [
            _vresult(details={"name": "Metformin"}),
            _vresult(details={"dosage": "500mg", "rx_number": "RX123",
                              "prescriber": "Dr. Smith"}),
        ]
        with patch(VISION_PATH, return_value=_mock_vision(results)):
            draft = process_capture_session(sess)
        ev = draft.extracted_values
        self.assertEqual(ev["name"], "Metformin")
        self.assertEqual(ev["dose"], "500mg")
        self.assertEqual(ev["rx_number"], "RX123")
        self.assertEqual(ev["provider"], "Dr. Smith")

    def test_real_scanitem_dataclass_handled(self):
        sess = _session(self.user, ["img1"])
        with patch(VISION_PATH, return_value=_mock_vision(
                [_vresult(details={"name": "Lisinopril", "dosage": "10mg"})])):
            draft = process_capture_session(sess)
        self.assertEqual(draft.extracted_values["name"], "Lisinopril")

    def test_confidence_improves_with_more_images(self):
        s1 = _session(self.user, ["a"])
        with patch(VISION_PATH, return_value=_mock_vision([_vresult(details={"name": "Lipitor"})])):
            process_capture_session(s1)
        s2 = _session(self.user, ["a", "b"])
        with patch(VISION_PATH, return_value=_mock_vision([
                _vresult(details={"name": "Lipitor"}),
                _vresult(details={"dosage": "20mg", "directions": "Take one daily",
                                  "rx_number": "RX9"})])):
            process_capture_session(s2)
        s1.refresh_from_db(); s2.refresh_from_db()
        self.assertGreater(s2.overall_confidence, s1.overall_confidence)

    def test_skip_optional_still_completes(self):
        sess = _session(self.user, ["a", "b"], profile="supplement", intake_type="supplement")
        results = [
            _vresult(category="supplement", details={"name": "Vitamin D"}),
            _vresult(category="supplement", details={"serving_size": "1 softgel"}),
        ]
        with patch(VISION_PATH, return_value=_mock_vision(results)):
            draft = process_capture_session(sess)
        self.assertEqual(draft.intake_type, Intake.INTAKE_TYPE_SUPPLEMENT)

    def test_unreadable_marks_failed_keeps_images(self):
        sess = _session(self.user, ["img1"])
        with patch(VISION_PATH, return_value=_mock_vision([_vresult(details={})])):
            draft = process_capture_session(sess)
        sess.refresh_from_db()
        self.assertIsNone(draft)
        self.assertEqual(sess.processing_status, MedicationCaptureSession.STATUS_FAILED)
        self.assertEqual(sess.images, ["img1"])  # kept for retry
        self.assertEqual(MedicationScanDraft.objects.filter(user=self.user).count(), 0)

    def test_vision_exception_propagates_for_retry(self):
        sess = _session(self.user, ["img1"])
        boom = MagicMock()
        boom.analyze_image.side_effect = ConnectionError("Vision timeout")
        with patch(VISION_PATH, return_value=boom):
            with self.assertRaises(ConnectionError):
                process_capture_session(sess)
        # Images preserved — the task will retry.
        sess.refresh_from_db()
        self.assertEqual(sess.images, ["img1"])


class CaptureTaskTest(AdherenceTestMixin, TestCase):
    """The Celery task wrapper (eager in tests)."""

    def setUp(self):
        self.user = self.create_user(email="captask@test.com")

    def test_task_success(self):
        from apps.health.tasks import process_medication_capture
        sess = _session(self.user, ["img1"])
        with patch(VISION_PATH, return_value=_mock_vision(
                [_vresult(details={"name": "Metformin", "dosage": "5mg"})])):
            result = process_medication_capture.apply(kwargs={"session_id": sess.id}).result
        sess.refresh_from_db()
        self.assertTrue(result["success"])
        self.assertEqual(sess.processing_status, MedicationCaptureSession.STATUS_READY)

    def test_task_non_retryable_failure_marks_failed(self):
        from apps.health.tasks import process_medication_capture
        sess = _session(self.user, ["img1"])
        with patch("apps.health.capture_session.process_capture_session",
                   side_effect=ValueError("bad data")):
            result = process_medication_capture.apply(kwargs={"session_id": sess.id}).result
        sess.refresh_from_db()
        self.assertFalse(result["success"])
        self.assertEqual(sess.processing_status, MedicationCaptureSession.STATUS_FAILED)

    def test_task_timeout_marks_failed(self):
        from apps.health.tasks import process_medication_capture
        sess = _session(self.user, ["img1"])
        with patch("apps.health.capture_session.process_capture_session",
                   side_effect=SoftTimeLimitExceeded()):
            result = process_medication_capture.apply(kwargs={"session_id": sess.id}).result
        sess.refresh_from_db()
        self.assertEqual(result["reason"], "timeout")
        self.assertEqual(sess.processing_status, MedicationCaptureSession.STATUS_FAILED)

    def test_task_does_not_reprocess_ready_session(self):
        from apps.health.tasks import process_medication_capture
        sess = _session(self.user, ["img1"])
        with patch(VISION_PATH, return_value=_mock_vision(
                [_vresult(details={"name": "Metformin", "dosage": "5mg"})])):
            process_medication_capture.apply(kwargs={"session_id": sess.id})
            # Re-run — must NOT create a second draft.
            process_medication_capture.apply(kwargs={"session_id": sess.id})
        self.assertEqual(MedicationScanDraft.objects.filter(user=self.user).count(), 1)

    def test_retryable_classifier(self):
        from apps.health.tasks import _capture_retryable
        self.assertTrue(_capture_retryable(Exception("Request timeout")))
        self.assertTrue(_capture_retryable(Exception("rate limit exceeded")))
        self.assertFalse(_capture_retryable(Exception("malformed image")))


class CaptureFlowViewTest(AdherenceTestMixin, TestCase):
    """The async endpoints. Celery is eager in tests, so the worker runs inline
    during start — letting us assert the end-to-end ready state."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user(email="capflow@test.com")
        self.client.force_login(self.user)
        from django.core.cache import cache
        cache.clear()  # reset rate-limit counters

    def _grant_consent(self):
        from apps.scan.models import ScanConsent
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.save()
        ScanConsent.objects.create(
            user=self.user, consent_version="1.0", consented_at=timezone.now())

    def _start(self, images, profile="prescription"):
        return self.client.post(
            reverse("health:medication_capture_start"),
            data=('{"images": %s, "intake_type": "medication", "profile": "%s"}'
                  % (str(images).replace("'", '"'), profile)),
            content_type="application/json")

    def test_start_requires_consent(self):
        resp = self._start(["img1"])
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"], "consent_required")
        self.assertEqual(MedicationCaptureSession.objects.count(), 0)

    def test_start_returns_202_immediately(self):
        self._grant_consent()
        with patch(VISION_PATH, return_value=_mock_vision(
                [_vresult(details={"name": "Metformin", "dosage": "500mg"})])):
            resp = self._start(["img1"])
        self.assertEqual(resp.status_code, 202)
        body = resp.json()
        self.assertIn("session_id", body)
        self.assertIn("status_url", body)

    def test_start_then_status_reaches_ready_with_review_url(self):
        self._grant_consent()
        with patch(VISION_PATH, return_value=_mock_vision(
                [_vresult(details={"name": "Metformin", "dosage": "500mg"}),
                 _vresult(details={"rx_number": "RX1"})])):
            resp = self._start(["img1", "img2"])
        sid = resp.json()["session_id"]
        status = self.client.get(
            reverse("health:medication_capture_status", kwargs={"session_id": sid})).json()
        self.assertEqual(status["status"], "ready")
        self.assertIn("/review/", status["review_url"])
        # One draft, nothing canonical.
        self.assertEqual(MedicationScanDraft.objects.filter(user=self.user).count(), 1)
        self.assertFalse(Intake.objects.filter(user=self.user).exists())

    def test_start_no_images_rejected(self):
        self._grant_consent()
        resp = self._start([])
        self.assertEqual(resp.status_code, 400)

    def test_status_reports_progress_while_analyzing(self):
        # Resume/poll semantics: a still-analyzing session reports progress, not done.
        self._grant_consent()
        sess = _session(self.user, ["a", "b"])
        sess.processing_status = MedicationCaptureSession.STATUS_ANALYZING
        sess.images_analyzed = 1
        sess.current_step = "Analyzing pharmacy label…"
        sess.save()
        status = self.client.get(
            reverse("health:medication_capture_status", kwargs={"session_id": sess.id})).json()
        self.assertEqual(status["status"], "analyzing")
        self.assertFalse(status["done"])
        self.assertEqual(status["images_analyzed"], 1)
        self.assertEqual(status["current_step"], "Analyzing pharmacy label…")

    def test_cancel_drops_images(self):
        self._grant_consent()
        sess = _session(self.user, ["a", "b"])
        resp = self.client.post(
            reverse("health:medication_capture_cancel", kwargs={"session_id": sess.id}))
        self.assertEqual(resp.status_code, 200)
        sess.refresh_from_db()
        self.assertEqual(sess.processing_status, MedicationCaptureSession.STATUS_CANCELLED)
        self.assertEqual(sess.images, [])

    def test_retry_failed_session_reaches_ready(self):
        self._grant_consent()
        sess = _session(self.user, ["img1"])
        sess.mark_failed("first attempt failed")
        with patch(VISION_PATH, return_value=_mock_vision(
                [_vresult(details={"name": "Metformin", "dosage": "500mg"})])):
            resp = self.client.post(
                reverse("health:medication_capture_retry", kwargs={"session_id": sess.id}),
                data="{}", content_type="application/json")
        self.assertEqual(resp.status_code, 202)
        sess.refresh_from_db()
        self.assertEqual(sess.processing_status, MedicationCaptureSession.STATUS_READY)
        self.assertEqual(sess.retry_count, 1)

    def test_large_cabinet_many_sessions_each_get_one_draft(self):
        """A whole medicine cabinet = many sessions; each yields exactly one draft,
        nothing canonical, no cross-contamination."""
        self._grant_consent()
        meds = ["Metformin", "Lisinopril", "Atorvastatin", "Levothyroxine",
                "Amlodipine", "Omeprazole"]
        for name in meds:
            with patch(VISION_PATH, return_value=_mock_vision(
                    [_vresult(details={"name": name, "dosage": "10mg"})])):
                resp = self._start(["img"], profile="prescription")
            self.assertEqual(resp.status_code, 202)
        self.assertEqual(MedicationScanDraft.objects.filter(user=self.user).count(), len(meds))
        self.assertFalse(Intake.objects.filter(user=self.user).exists())
