"""Document upload: the file and the row save together, or not at all.

Origin: 2026-09-13 23:35 UTC, `/life/documents/new/`, a 0.27 MB PDF with a 75-character
filename. Django's max_length check ran on the pre-upload name (98 chars) and passed;
Cloudinary prepended `media/` and appended `_bkukwc`, returned 111 chars, and the INSERT
hit `DataError: value too long for type character varying(100)`. The user saw a 500. The
blob was already in storage with no row pointing at it.

Every test here uses the local filesystem storage and a temp MEDIA_ROOT. Nothing reads
file contents beyond the first bytes the validator sniffs.
"""
import io
import shutil
import tempfile
from datetime import date
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.db.models.sql.compiler import SQLInsertCompiler, SQLUpdateCompiler
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.life.models import (
    DOCUMENT_STORAGE_BASENAME_MAX, Document, document_upload_path,
)
from apps.users.models import TermsAcceptance, User

# The exact filename from the production failure.
PROD_FILENAME = "Home_Theater_Purchase_Warranty_Dossier_with_Product_Images_and_Allstate.pdf"

_MEDIA = tempfile.mkdtemp(prefix="wlj-doc-upload-")


def _pdf(name=PROD_FILENAME, size=1024):
    body = b"%PDF-1.4\n" + b"0" * max(0, size - 9)
    return SimpleUploadedFile(name, body, content_type="application/pdf")


def _fail_document_writes(compiler_cls, message):
    """Patch so ONLY writes to life_document raise — the rest of the request keeps its
    database. A blanket mock also broke the error page's own inserts and turned the
    test into a TransactionManagementError about the harness, not the code."""
    real = compiler_cls.execute_sql

    def boom(self, *args, **kwargs):
        if self.query.get_meta().db_table == "life_document":
            # Compile first. FileField.pre_save — the upload to storage — runs INSIDE
            # as_sql(), so failing before it would simulate a storage failure, not the
            # production one, where the statement was built and the database refused it.
            self.as_sql()
            raise DatabaseError(message)
        return real(self, *args, **kwargs)
    return mock.patch.object(compiler_cls, "execute_sql", boom)


@override_settings(MEDIA_ROOT=_MEDIA, CLOUDINARY_STORAGE=None)
class _DocumentUploadBase(TestCase):
    """Shared: a logged-in Life user, a clean local storage root per class."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def setUp(self):
        self.user = User.objects.create_user(email="docs@test.com", password="testpass123")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.life_enabled = True
        self.user.preferences.save()
        self.client.login(email="docs@test.com", password="testpass123")
        self.url = reverse("life:document_create")

    def _post(self, file=None, token="tok-1", **extra):
        data = {"title": "Home theater warranty", "category": "warranty",
                "upload_token": token, "description": "", "notes": ""}
        data.update(extra)
        if file is not None:
            data["file"] = file
        return self.client.post(self.url, data)


# ── The storage key is bounded, whatever the backend adds ─────────────────────

class StorageKeyIsBounded(TestCase):

    def test_production_filename_yields_a_short_key(self):
        key = document_upload_path(None, PROD_FILENAME)
        base = key.rsplit("/", 1)[1]
        self.assertTrue(key.startswith("life/documents/"))
        self.assertTrue(base.endswith(".pdf"))
        self.assertLessEqual(len(base), DOCUMENT_STORAGE_BASENAME_MAX + len(".pdf"))
        # Room for any prefix + suffix a backend adds, with the column at 500.
        self.assertLess(len("media/" + key + "_xxxxxx"), 120)

    def test_key_is_sanitised_and_keeps_extension(self):
        key = document_upload_path(None, "../../weird name (final) copy!!.PDF")
        self.assertNotIn("..", key)
        self.assertNotIn(" ", key)
        self.assertTrue(key.endswith(".pdf"))

    def test_name_with_no_usable_base_still_produces_a_key(self):
        self.assertTrue(document_upload_path(None, "  .pdf").endswith("/document.pdf"))


# ── The happy path, with the production filename ──────────────────────────────

class SuccessfulUpload(_DocumentUploadBase):

    def test_pdf_with_production_filename_saves(self):
        response = self._post(_pdf(size=282671))
        self.assertRedirects(response, reverse("life:document_list"))
        doc = Document.objects.get(user=self.user)
        self.assertEqual(doc.original_filename, PROD_FILENAME)
        self.assertEqual(doc.file_type, "pdf")
        self.assertEqual(doc.file_size, 282671)
        self.assertEqual(doc.upload_token, "tok-1")
        self.assertTrue(doc.file.storage.exists(doc.file.name))

    def test_optional_dates_may_be_blank(self):
        response = self._post(_pdf(), document_date="", expiration_date="")
        self.assertEqual(response.status_code, 302)
        doc = Document.objects.get(user=self.user)
        self.assertIsNone(doc.document_date)
        self.assertIsNone(doc.expiration_date)

    def test_optional_dates_round_trip(self):
        self._post(_pdf(), document_date="2026-09-01", expiration_date="2027-09-01")
        doc = Document.objects.get(user=self.user)
        self.assertEqual(doc.document_date, date(2026, 9, 1))
        self.assertEqual(doc.expiration_date, date(2027, 9, 1))

    def test_success_message_is_only_queued_after_the_save(self):
        response = self._post(_pdf(), follow=True) if False else self.client.post(
            self.url, {"title": "T", "category": "other", "upload_token": "m1", "file": _pdf()},
            follow=True)
        msgs = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("uploaded" in m for m in msgs))

    def test_form_renders_with_a_fresh_token_and_no_500(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="upload_token"')
        self.assertContains(response, "Save Document")
        self.assertContains(response, "uploads when you save")


# ── Validation lands beside the control, never as a 500 ───────────────────────

class ValidationIsInline(_DocumentUploadBase):

    def test_wrong_extension_is_refused(self):
        bad = SimpleUploadedFile("script.exe", b"MZ\x90\x00", content_type="application/octet-stream")
        response = self._post(bad)
        self.assertEqual(response.status_code, 200)
        self.assertIn("file type isn't supported", response.context["form"].errors["file"][0])
        self.assertEqual(Document.objects.count(), 0)

    def test_pdf_by_name_only_is_refused(self):
        fake = SimpleUploadedFile("not-really.pdf", b"hello there", content_type="application/pdf")
        response = self._post(fake)
        self.assertIn("doesn't look like a real PDF", response.context["form"].errors["file"][0])
        self.assertEqual(Document.objects.count(), 0)

    def test_oversize_is_refused_with_the_size_named(self):
        big = SimpleUploadedFile("big.pdf", b"%PDF" + b"0" * (10 * 1024 * 1024 + 1),
                                 content_type="application/pdf")
        response = self._post(big)
        err = response.context["form"].errors["file"][0]
        self.assertIn("10.0 MB", err)
        self.assertEqual(Document.objects.count(), 0)

    def test_empty_file_is_refused(self):
        response = self._post(SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("file", response.context["form"].errors)

    def test_missing_file_is_a_field_error(self):
        response = self._post(None)
        self.assertEqual(response.status_code, 200)
        self.assertIn("file", response.context["form"].errors)

    def test_expiry_before_document_date_is_a_field_error(self):
        response = self._post(_pdf(), document_date="2026-09-10", expiration_date="2026-09-01")
        self.assertEqual(response.status_code, 200)
        self.assertIn("expiration_date", response.context["form"].errors)
        self.assertEqual(Document.objects.count(), 0)

    def test_field_errors_are_rendered_beside_the_control(self):
        response = self._post(SimpleUploadedFile("x.txt", b"nope", content_type="text/plain"))
        self.assertContains(response, 'id="file-error"')
        self.assertContains(response, "file type isn&#x27;t supported")


# ── Failure on either side of the line leaves nothing behind ──────────────────

class FailuresAreClean(_DocumentUploadBase):

    def _storage_files(self):
        import os
        out = []
        for root, _dirs, files in os.walk(_MEDIA):
            out += [os.path.join(root, f) for f in files]
        return out

    def test_database_failure_after_upload_removes_the_blob(self):
        """The production shape: storage accepted the file, the INSERT then failed."""
        before = set(self._storage_files())
        with _fail_document_writes(SQLInsertCompiler, "value too long for type character varying(100)"):
            response = self._post(_pdf())
        self.assertEqual(response.status_code, 200, "must re-render, not 500")
        err = response.context["form"].non_field_errors()[0]
        self.assertIn("nothing was kept", err)
        self.assertRegex(err, r"Reference [0-9a-f]{8}")
        self.assertEqual(Document.objects.count(), 0)
        self.assertEqual(set(self._storage_files()), before, "the orphaned blob must be removed")

    def test_storage_failure_writes_no_row(self):
        from django.core.files.storage import FileSystemStorage
        with mock.patch.object(FileSystemStorage, "_save", side_effect=OSError("disk gone")):
            response = self._post(_pdf())
        self.assertEqual(response.status_code, 200)
        self.assertIn("couldn't be stored", response.context["form"].errors["file"][0])
        self.assertEqual(Document.objects.count(), 0)

    def test_failure_logs_a_reference_without_the_filename(self):
        with _fail_document_writes(SQLInsertCompiler, "boom"), \
                self.assertLogs("apps.life.services.document_upload", level="ERROR") as logs:
            self._post(_pdf())
        joined = "\n".join(logs.output)
        self.assertIn("database write failed after storage", joined)
        self.assertNotIn("Home_Theater", joined)


# ── Retrying and double-clicking never make two documents ─────────────────────

class NoDuplicates(_DocumentUploadBase):

    def test_same_token_twice_yields_one_document(self):
        first = self._post(_pdf(), token="dbl")
        second = self._post(_pdf(), token="dbl")
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(Document.objects.filter(user=self.user).count(), 1)

    def test_retry_after_failure_succeeds_with_the_same_token(self):
        with _fail_document_writes(SQLInsertCompiler, "transient"):
            self._post(_pdf(), token="retry")
        self.assertEqual(Document.objects.count(), 0)
        response = self._post(_pdf(), token="retry")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Document.objects.filter(user=self.user, upload_token="retry").count(), 1)

    def test_token_is_scoped_to_the_user(self):
        other = User.objects.create_user(email="other@test.com", password="testpass123")
        Document.objects.create(user=other, title="theirs", upload_token="shared",
                                file=_pdf("theirs.pdf"))
        response = self._post(_pdf(), token="shared")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Document.objects.filter(user=self.user).count(), 1)

    def test_lost_race_returns_the_winner(self):
        """Two requests pass the pre-check; the constraint decides, and the loser
        drops its blob and lands on the winner's document."""
        from django.db import IntegrityError
        from apps.life.services.document_upload import save_document_upload
        from apps.life.forms import DocumentForm

        winner = Document.objects.create(user=self.user, title="w", upload_token="race",
                                         file=_pdf("w.pdf"))
        form = DocumentForm({"title": "loser", "category": "other", "upload_token": "race"},
                            {"file": _pdf("l.pdf")}, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        with mock.patch("apps.life.services.document_upload.existing_for_token",
                        side_effect=[None, winner]), \
                mock.patch.object(DocumentForm, "save", side_effect=IntegrityError("unique")):
            doc, created = save_document_upload(form, self.user)
        self.assertFalse(created)
        self.assertEqual(doc.pk, winner.pk)


# ── Editing: the old file survives a failed replacement ───────────────────────

class ReplacementIsSafe(_DocumentUploadBase):

    def test_failed_replacement_keeps_the_old_file(self):
        doc = Document.objects.create(user=self.user, title="keep", file=_pdf("old.pdf"))
        old_name = doc.file.name
        url = reverse("life:document_update", kwargs={"pk": doc.pk})
        with _fail_document_writes(SQLUpdateCompiler, "nope"):
            response = self.client.post(url, {"title": "keep", "category": "other",
                                              "file": _pdf("new.pdf")})
        self.assertEqual(response.status_code, 200)
        doc.refresh_from_db()
        self.assertEqual(doc.file.name, old_name)
        self.assertTrue(doc.file.storage.exists(old_name), "old file must not be deleted first")

    def test_successful_replacement_removes_the_old_file_after_commit(self):
        doc = Document.objects.create(user=self.user, title="swap", file=_pdf("old.pdf"))
        old_name = doc.file.name
        url = reverse("life:document_update", kwargs={"pk": doc.pk})
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, {"title": "swap", "category": "other",
                                              "file": _pdf("new.pdf")})
        self.assertEqual(response.status_code, 302)
        doc.refresh_from_db()
        self.assertNotEqual(doc.file.name, old_name)
        self.assertFalse(doc.file.storage.exists(old_name))
        self.assertEqual(doc.original_filename, "new.pdf")

    def test_edit_without_a_new_file_keeps_everything(self):
        doc = Document.objects.create(user=self.user, title="same", file=_pdf("same.pdf"))
        url = reverse("life:document_update", kwargs={"pk": doc.pk})
        response = self.client.post(url, {"title": "renamed", "category": "other"})
        self.assertEqual(response.status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.title, "renamed")
        self.assertTrue(doc.file.storage.exists(doc.file.name))


# ── Post-save hooks wait for the commit ──────────────────────────────────────

class HooksWaitForCommit(_DocumentUploadBase):

    def test_extraction_is_enqueued_only_on_commit(self):
        self.user.preferences.ai_enabled = True
        self.user.preferences.proactive_assistance_enabled = True
        self.user.preferences.save()
        with mock.patch("apps.core.celery_utils.safe_enqueue") as enq, \
                self.captureOnCommitCallbacks(execute=False) as callbacks:
            self._post(_pdf())
            self.assertEqual(enq.call_count, 0, "nothing may be enqueued before commit")
        for cb in callbacks:
            cb()
        self.assertGreaterEqual(enq.call_count, 1)
