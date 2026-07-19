"""
Tests for the universal attachment validator (all content classes) and the
dedicated upload endpoint.

Proves: byte-sniffing across images/documents/audio/video, extension-assisted
Office/text disambiguation, per-class size caps, graceful unsupported-type
rejection, and end-to-end durable-artifact creation via the endpoint.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.ai.upload_validation import (
    KIND_AUDIO,
    KIND_DOCUMENT,
    KIND_IMAGE,
    KIND_VIDEO,
    MAX_BYTES,
    UploadValidationError,
    sniff_content_type,
    validate_attachment,
)
from apps.capture.models import MultimodalArtifact

User = get_user_model()

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF = b"%PDF-1.7\n" + b"x" * 32
WAV = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 16
MP3 = b"ID3" + b"\x00" * 32
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16
MOV = b"\x00\x00\x00\x18ftypqt  " + b"\x00" * 16
M4A = b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 16
TIFF = b"II*\x00" + b"\x00" * 16
ZIP = b"PK\x03\x04" + b"\x00" * 32  # office container / bare zip
TXT = b"just some plain text\nsecond line\n"


class SniffTests(TestCase):
    def test_sniffs_each_class(self):
        self.assertEqual(sniff_content_type(PNG), "image/png")
        self.assertEqual(sniff_content_type(TIFF), "image/tiff")
        self.assertEqual(sniff_content_type(PDF), "application/pdf")
        self.assertEqual(sniff_content_type(WAV), "audio/wav")
        self.assertEqual(sniff_content_type(MP3), "audio/mpeg")
        self.assertEqual(sniff_content_type(MP4), "video/mp4")
        self.assertEqual(sniff_content_type(MOV), "video/quicktime")
        self.assertEqual(sniff_content_type(M4A), "audio/mp4")

    def test_office_needs_extension(self):
        # A zip container is only an Office doc with the right extension.
        self.assertIsNone(sniff_content_type(ZIP))  # bare zip → unsupported
        self.assertEqual(
            sniff_content_type(ZIP, "report.docx"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual(
            sniff_content_type(ZIP, "sheet.xlsx"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_text_by_extension_and_content(self):
        self.assertEqual(sniff_content_type(TXT, "notes.txt"), "text/plain")
        self.assertEqual(sniff_content_type(TXT, "data.csv"), "text/csv")
        # Binary content with a .txt name is NOT text.
        self.assertIsNone(sniff_content_type(b"\x00\x01\x02\x03", "fake.txt"))


class ValidateAttachmentTests(TestCase):
    def test_valid_kinds(self):
        self.assertEqual(validate_attachment(PNG, filename="a.png")["kind"], KIND_IMAGE)
        self.assertEqual(validate_attachment(PDF, filename="a.pdf")["kind"], KIND_DOCUMENT)
        self.assertEqual(validate_attachment(MP3, filename="a.mp3")["kind"], KIND_AUDIO)
        self.assertEqual(validate_attachment(MP4, filename="a.mp4")["kind"], KIND_VIDEO)
        self.assertEqual(validate_attachment(TXT, filename="a.txt")["kind"], KIND_DOCUMENT)

    def test_empty_rejected(self):
        with self.assertRaises(UploadValidationError):
            validate_attachment(b"", filename="a.png")

    def test_unsupported_rejected(self):
        with self.assertRaises(UploadValidationError):
            validate_attachment(b"\x00\x01\x02\x03\x04\x05\x06", filename="a.bin")

    def test_oversize_rejected(self):
        big = PDF + b"x" * (MAX_BYTES[KIND_DOCUMENT] + 1)
        with self.assertRaises(UploadValidationError):
            validate_attachment(big, filename="a.pdf")


@override_settings(MEDIA_ROOT="/tmp/wlj-attach-endpoint-test")
class UploadEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="up@example.com", password="pw12345!")
        from apps.users.models import TermsAcceptance
        from django.conf import settings
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS["TERMS_VERSION"],
        )
        prefs = self.user.preferences
        prefs.has_completed_onboarding = True
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.save()
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse("ai:api_attachments")

    def test_uploads_pdf_creates_artifact(self):
        resp = self.client.post(self.url, data={"file": _named_file("report.pdf", PDF, "application/pdf")})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        att = body["attachments"][0]
        self.assertEqual(att["kind"], KIND_DOCUMENT)
        self.assertEqual(att["content_type"], "application/pdf")
        self.assertTrue(MultimodalArtifact.objects.filter(id=att["artifact_id"], user=self.user).exists())

    def test_unsupported_type_rejected(self):
        resp = self.client.post(self.url, data={"file": _named_file("x.bin", b"\x00\x01\x02\x03\x04", "application/octet-stream")})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_no_file(self):
        resp = self.client.post(self.url, data={})
        self.assertEqual(resp.status_code, 400)


def _named_file(name, content, content_type):
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, content, content_type=content_type)
