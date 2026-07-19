"""
Tests for Phase 1.3 Milestone 1 — PDF perception.

Deterministic extraction (pdfplumber) → stored on the artifact → surfaced to the
model through the arrival path. WLJ decodes; the model reasons.
"""
import base64
import io

import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai.multimodal import attachments_from_ids, store_and_persist_artifact
from apps.ai.perception import is_perceivable, perceive
from apps.ai.tasks import perceive_artifact
from apps.capture.models import MultimodalArtifact

User = get_user_model()


def _make_pdf(pages):
    """pages = list of list-of-lines; each inner list is one PDF page."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for lines in pages:
        y = 750
        for line in lines:
            c.drawString(72, y, line)
            y -= 20
        c.showPage()
    c.save()
    return buf.getvalue()


class PerceiveModuleTests(TestCase):
    def test_extracts_pdf_text_and_pages(self):
        pdf = _make_pdf([
            ["Insurance Policy", "Deductible: $1,500", "Provider: ACME Health"],
            ["Coverage: 80%", "Out-of-pocket max: $6,000"],
        ])
        result = perceive("application/pdf", pdf)
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["page_count"], 2)
        self.assertIn("Deductible: $1,500", result["text"])
        self.assertIn("Out-of-pocket max: $6,000", result["text"])
        self.assertIn("[Page 1]", result["text"])
        self.assertIn("[Page 2]", result["text"])

    def test_unsupported_type(self):
        result = perceive("application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK\x03\x04")
        self.assertEqual(result["status"], "unsupported")

    def test_corrupt_pdf_fails_gracefully(self):
        result = perceive("application/pdf", b"%PDF-1.7 not really a pdf")
        self.assertIn(result["status"], ("failed", "unsupported"))
        self.assertEqual(result["text"], "")

    def test_is_perceivable(self):
        self.assertTrue(is_perceivable("application/pdf"))
        self.assertFalse(is_perceivable("image/png"))
        self.assertFalse(is_perceivable(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))  # Office = later


class PerceiveArtifactTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="p@ex.com", password="x")

    def test_task_populates_extracted_text(self):
        pdf = _make_pdf([["Lab Report", "Glucose: 95 mg/dL", "Cholesterol: 180"]])
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="p" * 64, content_type="application/pdf",
            kind="document", perception_status=MultimodalArtifact.PERCEPTION_PENDING,
        )
        result = perceive_artifact(art.id, base64.b64encode(pdf).decode())
        self.assertEqual(result["result"], "done")
        art.refresh_from_db()
        self.assertTrue(art.has_perception)
        self.assertIn("Glucose: 95 mg/dL", art.extracted_text)
        self.assertEqual(art.page_count, 1)

    def test_task_idempotent(self):
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="q" * 64, content_type="application/pdf", kind="document",
            perception_status=MultimodalArtifact.PERCEPTION_DONE, extracted_text="already",
        )
        result = perceive_artifact(art.id, "")
        self.assertEqual(result["result"], "already_perceived")


class AttachmentSurfacingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="s@ex.com", password="x")

    def test_perceived_document_surfaces_text(self):
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="a" * 64, content_type="application/pdf", kind="document",
            perception_status=MultimodalArtifact.PERCEPTION_DONE,
            extracted_text="[Page 1]\nDeductible: $1,500", page_count=1,
        )
        out = attachments_from_ids(self.user, [art.id])
        self.assertEqual(len(out), 1)
        self.assertIn("Deductible: $1,500", out[0]["text"])
        self.assertEqual(out[0]["page_count"], 1)

    def test_pending_document_signals_processing(self):
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="b" * 64, content_type="application/pdf", kind="document",
            perception_status=MultimodalArtifact.PERCEPTION_PENDING,
        )
        out = attachments_from_ids(self.user, [art.id])
        self.assertEqual(out[0].get("perception"), "processing")
        self.assertNotIn("text", out[0])

    def test_image_has_no_text(self):
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="c" * 64, content_type="image/png", kind="image",
            perception_status=MultimodalArtifact.PERCEPTION_NONE,
        )
        out = attachments_from_ids(self.user, [art.id])
        self.assertNotIn("text", out[0])
        self.assertNotIn("perception", out[0])

    def test_owner_scoped(self):
        other = User.objects.create_user(email="o@ex.com", password="x")
        art = MultimodalArtifact.objects.create(
            user=other, sha256="d" * 64, content_type="application/pdf", kind="document",
            perception_status=MultimodalArtifact.PERCEPTION_DONE, extracted_text="secret",
        )
        self.assertEqual(attachments_from_ids(self.user, [art.id]), [])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="wlj-perceive-e2e-"))
class EndToEndArrivalTests(TestCase):
    """The shared intake primitive stores AND perceives (eager celery here)."""

    def setUp(self):
        self.user = User.objects.create_user(email="e2e@ex.com", password="x")

    def test_store_and_persist_perceives_pdf(self):
        pdf = _make_pdf([["Compensation Plan", "Base salary: $120,000", "Bonus target: 15%"]])
        art, _ = store_and_persist_artifact(
            self.user, data=pdf, content_type="application/pdf", kind="document",
        )
        art.refresh_from_db()
        # Durable storage AND deterministic perception both ran in the background.
        self.assertTrue(art.is_durably_stored)
        self.assertTrue(art.has_perception)
        self.assertIn("Base salary: $120,000", art.extracted_text)
        # And it surfaces to the model through the arrival path.
        out = attachments_from_ids(self.user, [art.id])
        self.assertIn("Bonus target: 15%", out[0]["text"])
