"""
Milestone C — Artifact Library / detail / Current Context render + behavior tests.
"""
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.capture.models import MultimodalArtifact

User = get_user_model()
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


def _login_user(email):
    from django.conf import settings

    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS["TERMS_VERSION"])
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="wlj-lib-"))
class ArtifactLibraryViewTests(TestCase):
    def setUp(self):
        self.user = _login_user("lib@example.com")
        self.client.force_login(self.user)
        self.pdf = MultimodalArtifact.objects.create(
            user=self.user, sha256="a" * 64, content_type="application/pdf", kind="document",
            original_filename="insurance_policy.pdf", perception_status="done",
            extracted_text="Deductible: $1,500. Emergency care covered.", page_count=3,
            source_conversation_id=42, associations=["project:5"])
        name = default_storage.save("multimodal/x/pic.png", ContentFile(PNG))
        self.img = MultimodalArtifact.objects.create(
            user=self.user, sha256="b" * 64, content_type="image/png", kind="image",
            original_filename="progress.png", storage_ref=name,
            storage_status=MultimodalArtifact.STORAGE_STORED)

    def test_library_lists_uploads_and_declares_context(self):
        resp = self.client.get(reverse("capture:artifact_library"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("insurance_policy.pdf", body)
        self.assertIn("progress.png", body)
        self.assertIn('content="summary:artifacts.library"', body)   # Current Context

    def test_library_search_filters(self):
        resp = self.client.get(reverse("capture:artifact_library"), {"q": "insurance"})
        body = resp.content.decode()
        self.assertIn("insurance_policy.pdf", body)
        self.assertNotIn("progress.png", body)

    def test_library_kind_filter(self):
        resp = self.client.get(reverse("capture:artifact_library"), {"kind": "image"})
        body = resp.content.decode()
        self.assertIn("progress.png", body)
        self.assertNotIn("insurance_policy.pdf", body)

    def test_detail_shows_content_and_provenance(self):
        resp = self.client.get(reverse("capture:artifact_detail", args=[self.pdf.id]))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Deductible: $1,500", body)         # what WLJ read
        self.assertIn("project:5", body)                  # domain link
        self.assertIn("conversation=42", body)            # link back to conversation
        self.assertIn('content="summary:artifacts.detail;id=', body)  # Current Context object

    def test_detail_owner_scoped(self):
        other = _login_user("other@example.com")
        art = MultimodalArtifact.objects.create(
            user=other, sha256="c" * 64, content_type="application/pdf", kind="document")
        resp = self.client.get(reverse("capture:artifact_detail", args=[art.id]))
        self.assertEqual(resp.status_code, 404)

    def test_download_serves_bytes_owner_scoped(self):
        resp = self.client.get(reverse("capture:artifact_download", args=[self.img.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b"".join(resp.streaming_content), PNG)
        # other user cannot download it
        MultimodalArtifact.objects.filter(id=self.img.id).update(
            user=_login_user("z@example.com"))
        resp2 = self.client.get(reverse("capture:artifact_download", args=[self.img.id]))
        self.assertEqual(resp2.status_code, 404)

    def test_page_summary_providers(self):
        from apps.core.current_context import _PAGE_SUMMARY_PROVIDERS
        lib = _PAGE_SUMMARY_PROVIDERS["artifacts.library"](self.user, {})
        self.assertIn("Uploads library", lib["content"])
        det = _PAGE_SUMMARY_PROVIDERS["artifacts.detail"](self.user, {"id": self.pdf.id})
        self.assertIn("Deductible", det["content"])
        self.assertIn("insurance_policy.pdf", det["title"])
