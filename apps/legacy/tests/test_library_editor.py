"""Slice 2 tests — Memory Library + Editor (CRUD, status, provenance, media)."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.legacy.models import Media, Memory, MemoryRevision

User = get_user_model()


def _make_user(email="keeper@example.com"):
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class LibraryViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)
        self.draft = Memory.objects.create(user=self.user, title="Draft one", body="hello world")
        self.legacy = Memory.objects.create(
            user=self.user, title="Kept one", body="a kept memory",
            entry_state=Memory.EntryState.LEGACY,
        )
        self.archived = Memory.objects.create(user=self.user, title="Old one")
        self.archived.archive()

    def test_library_renders_cards(self):
        resp = self.client.get(reverse("legacy:library"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "legacy/library.html")
        self.assertContains(resp, "Draft one")
        self.assertContains(resp, "Kept one")
        self.assertNotContains(resp, "Old one")  # archived hidden by default

    def test_list_view_mode(self):
        resp = self.client.get(reverse("legacy:library"), {"view": "list"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "mlist")

    def test_status_filter_draft_vs_legacy(self):
        r_draft = self.client.get(reverse("legacy:library"), {"status": "draft"})
        self.assertContains(r_draft, "Draft one")
        self.assertNotContains(r_draft, "Kept one")
        r_legacy = self.client.get(reverse("legacy:library"), {"status": "legacy"})
        self.assertContains(r_legacy, "Kept one")
        self.assertNotContains(r_legacy, "Draft one")

    def test_status_filter_archived(self):
        r = self.client.get(reverse("legacy:library"), {"status": "archived"})
        self.assertContains(r, "Old one")
        self.assertNotContains(r, "Draft one")

    def test_search(self):
        r = self.client.get(reverse("legacy:library"), {"q": "kept"})
        self.assertContains(r, "Kept one")
        self.assertNotContains(r, "Draft one")

    def test_timeframe_year_includes_recent(self):
        r = self.client.get(reverse("legacy:library"), {"tf": "year"})
        self.assertContains(r, "Draft one")

    def test_empty_state_when_filtered_out(self):
        r = self.client.get(reverse("legacy:library"), {"q": "zzz-nomatch"})
        self.assertContains(r, "No memories match")

    def test_login_required(self):
        self.client.logout()
        r = self.client.get(reverse("legacy:library"))
        self.assertEqual(r.status_code, 302)


class EditorViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.other = _make_user("other@example.com")
        self.client.force_login(self.user)
        self.memory = Memory.objects.create(user=self.user, title="Mine", body="text")

    def test_new_editor_renders(self):
        r = self.client.get(reverse("legacy:editor_new"))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "legacy/editor.html")

    def test_edit_own_memory(self):
        r = self.client.get(reverse("legacy:editor", args=[self.memory.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Mine")

    def test_cannot_edit_others_memory(self):
        other_mem = Memory.objects.create(user=self.other, title="Theirs")
        r = self.client.get(reverse("legacy:editor", args=[other_mem.pk]))
        self.assertEqual(r.status_code, 404)


class SaveTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    def test_create_draft_via_autosave_returns_json(self):
        r = self.client.post(
            reverse("legacy:memory_save"),
            {"pk": "", "title": "New", "body": "body", "action": "autosave"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        m = Memory.objects.get(pk=data["pk"])
        self.assertEqual(m.entry_state, Memory.EntryState.DRAFT)
        self.assertEqual(m.created_via, Memory.CREATED_VIA_MANUAL)
        self.assertEqual(m.source_kind, Memory.SourceKind.OWNER)

    def test_save_draft_redirects(self):
        r = self.client.post(reverse("legacy:memory_save"),
                             {"pk": "", "title": "D", "body": "b", "action": "draft"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Memory.objects.filter(title="D", entry_state="draft").exists())

    def test_add_to_legacy_transition(self):
        m = Memory.objects.create(user=self.user, title="X", body="y")
        r = self.client.post(reverse("legacy:memory_save"),
                             {"pk": m.pk, "title": "X", "body": "y2", "action": "legacy"})
        self.assertEqual(r.status_code, 302)
        m.refresh_from_db()
        self.assertEqual(m.entry_state, Memory.EntryState.LEGACY)
        self.assertEqual(m.updated_by, self.user)

    def test_editing_legacy_memory_creates_revision(self):
        m = Memory.objects.create(user=self.user, title="Canon", body="v1",
                                  entry_state=Memory.EntryState.LEGACY)
        self.assertEqual(m.revisions.count(), 0)
        self.client.post(reverse("legacy:memory_save"),
                         {"pk": m.pk, "title": "Canon", "body": "v2 deeper", "action": "legacy"})
        m.refresh_from_db()
        self.assertEqual(m.body, "v2 deeper")
        self.assertEqual(m.revisions.count(), 1)          # prior telling preserved
        self.assertEqual(m.revisions.first().body, "v1")

    def test_editing_draft_does_not_create_revision(self):
        m = Memory.objects.create(user=self.user, title="D", body="v1")
        self.client.post(reverse("legacy:memory_save"),
                         {"pk": m.pk, "title": "D", "body": "v2", "action": "draft"})
        m.refresh_from_db()
        self.assertEqual(m.revisions.count(), 0)


class ArchiveRestoreTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)
        self.memory = Memory.objects.create(user=self.user, title="Z")

    def test_archive_then_restore(self):
        self.client.post(reverse("legacy:memory_archive", args=[self.memory.pk]))
        self.memory.refresh_from_db()
        self.assertEqual(self.memory.status, "archived")
        self.assertFalse(Memory.objects.filter(pk=self.memory.pk).exists())  # hidden by manager

        self.client.post(reverse("legacy:memory_restore", args=[self.memory.pk]))
        self.memory.refresh_from_db()
        self.assertEqual(self.memory.status, "active")
        self.assertTrue(Memory.objects.filter(pk=self.memory.pk).exists())

    def test_delete_forever_only_when_archived(self):
        m = Memory.objects.create(user=self.user, title="X")
        # Not archived → refuses; memory still exists.
        self.client.post(reverse("legacy:memory_delete_forever", args=[m.pk]))
        self.assertTrue(Memory.all_objects.filter(pk=m.pk).exists())
        # Archive, then delete forever → gone for good.
        m.archive()
        self.client.post(reverse("legacy:memory_delete_forever", args=[m.pk]))
        self.assertFalse(Memory.all_objects.filter(pk=m.pk).exists())

    def test_cannot_delete_others_memory(self):
        other = _make_user("stranger@example.com")
        om = Memory.objects.create(user=other, title="Theirs")
        om.archive()
        r = self.client.post(reverse("legacy:memory_delete_forever", args=[om.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Memory.all_objects.filter(pk=om.pk).exists())

    def test_full_status_lifecycle(self):
        m = Memory.objects.create(user=self.user, title="Life")
        self.assertEqual(m.entry_state, "draft")
        self.client.post(reverse("legacy:memory_save"),
                         {"pk": m.pk, "title": "Life", "body": "b", "action": "legacy"})
        m.refresh_from_db(); self.assertEqual(m.entry_state, "legacy")
        self.client.post(reverse("legacy:memory_archive", args=[m.pk]))
        m.refresh_from_db(); self.assertEqual(m.status, "archived")
        self.client.post(reverse("legacy:memory_restore", args=[m.pk]))
        m.refresh_from_db(); self.assertEqual(m.status, "active")


class MediaUploadTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)
        self.memory = Memory.objects.create(user=self.user, title="With media")

    def test_upload_attaches_media(self):
        img = SimpleUploadedFile("photo.jpg", b"fakeimagebytes", content_type="image/jpeg")
        r = self.client.post(reverse("legacy:memory_media_add", args=[self.memory.pk]), {"file": img})
        self.assertEqual(r.status_code, 302)
        self.memory.refresh_from_db()
        self.assertEqual(self.memory.media.count(), 1)
        media = self.memory.media.first()
        self.assertEqual(media.media_type, Media.MediaType.PHOTO)
        self.assertEqual(self.memory.primary_media_id, media.id)
