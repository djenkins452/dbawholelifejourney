"""
Tests for Notes views.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import Tag
from apps.notes.models import Note

User = get_user_model()


class NoteViewTestMixin:
    """Common setup for note view tests."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="noteview@example.com", password="testpass123"
        )
        self._accept_terms(self.user)
        self._complete_onboarding(self.user)
        self.client.login(email="noteview@example.com", password="testpass123")

    def _accept_terms(self, user):
        try:
            from django.conf import settings

            from apps.users.models import TermsAcceptance

            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
            )
        except Exception:
            pass

    def _complete_onboarding(self, user):
        try:
            user.preferences.has_completed_onboarding = True
            user.preferences.save()
        except Exception:
            pass


class NoteListViewTest(NoteViewTestMixin, TestCase):
    """Tests for the notes list view."""

    def test_requires_login(self):
        """Anonymous users are redirected."""
        self.client.logout()
        response = self.client.get(reverse("notes:note_list"))
        self.assertEqual(response.status_code, 302)

    def test_list_notes(self):
        """Authenticated user sees their notes."""
        Note.objects.create(user=self.user, body="My note")
        response = self.client.get(reverse("notes:note_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My note")

    def test_user_isolation(self):
        """Cannot see other user's notes."""
        other = User.objects.create_user(
            email="other@example.com", password="testpass123"
        )
        Note.objects.create(user=self.user, body="My note")
        Note.objects.create(user=other, body="Their note")
        response = self.client.get(reverse("notes:note_list"))
        self.assertContains(response, "My note")
        self.assertNotContains(response, "Their note")

    def test_search_filter(self):
        """Search filters notes by title and body."""
        Note.objects.create(user=self.user, body="Alpha note content")
        Note.objects.create(user=self.user, body="Beta note content")
        response = self.client.get(reverse("notes:note_list") + "?search=Alpha")
        self.assertContains(response, "Alpha")
        self.assertNotContains(response, "Beta note content")

    def test_tag_filter(self):
        """Filter by tag ID works."""
        tag = Tag.objects.create(user=self.user, name="urgent", color="#ef4444")
        note1 = Note.objects.create(user=self.user, body="Tagged note")
        note1.tags.add(tag)
        Note.objects.create(user=self.user, body="Untagged note")
        response = self.client.get(
            reverse("notes:note_list") + f"?tag={tag.id}"
        )
        self.assertContains(response, "Tagged note")
        self.assertNotContains(response, "Untagged note")

    def test_color_filter(self):
        """Filter by color works."""
        Note.objects.create(user=self.user, body="Red note", color="red")
        Note.objects.create(user=self.user, body="Blue note", color="blue")
        response = self.client.get(reverse("notes:note_list") + "?color=red")
        self.assertContains(response, "Red note")
        self.assertNotContains(response, "Blue note")

    def test_pinned_filter(self):
        """Filter by pinned status works."""
        Note.objects.create(user=self.user, body="Pinned", is_pinned=True)
        Note.objects.create(user=self.user, body="Not pinned", is_pinned=False)
        response = self.client.get(reverse("notes:note_list") + "?pinned=1")
        self.assertContains(response, "Pinned")
        # "Not pinned" contains "Pinned" substring, so check more specifically
        notes = response.context["notes"]
        self.assertEqual(notes.count(), 1)
        self.assertTrue(notes.first().is_pinned)


class NoteFullTextSearchViewTest(NoteViewTestMixin, TestCase):
    """Tests for full-text search via the ?q= parameter."""

    def test_fulltext_search_returns_matching_notes(self):
        """Full-text search finds notes containing the query."""
        Note.objects.create(
            user=self.user, title="Kubernetes Strategy", body="Deploy to production"
        )
        Note.objects.create(
            user=self.user, body="Grocery list for the week"
        )
        response = self.client.get(reverse("notes:note_list") + "?q=kubernetes")
        self.assertEqual(response.status_code, 200)
        notes = response.context["notes"]
        self.assertEqual(len(list(notes)), 1)
        self.assertContains(response, "Kubernetes")

    def test_fulltext_search_ranks_title_higher(self):
        """Title matches rank above body-only matches."""
        Note.objects.create(
            user=self.user,
            title="DevOps pipeline",
            body="General infrastructure notes",
        )
        Note.objects.create(
            user=self.user,
            title="Meeting notes",
            body="We discussed the DevOps pipeline improvements",
        )
        response = self.client.get(reverse("notes:note_list") + "?q=devops+pipeline")
        notes = list(response.context["notes"])
        self.assertEqual(len(notes), 2)
        # Title match should be first
        self.assertEqual(notes[0].title, "DevOps pipeline")

    def test_fulltext_search_respects_user_isolation(self):
        """Full-text search only returns the current user's notes."""
        other = User.objects.create_user(
            email="search_other@example.com", password="testpass123"
        )
        Note.objects.create(user=self.user, body="Secret project notes")
        Note.objects.create(user=other, body="Secret project info from other")
        response = self.client.get(reverse("notes:note_list") + "?q=secret+project")
        notes = list(response.context["notes"])
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].user, self.user)

    def test_fulltext_search_no_results(self):
        """Search with no matches returns empty list."""
        Note.objects.create(user=self.user, body="Regular everyday note")
        response = self.client.get(
            reverse("notes:note_list") + "?q=zzzyyyxxx"
        )
        notes = list(response.context["notes"])
        self.assertEqual(len(notes), 0)
        self.assertTrue(response.context["is_searching"])

    def test_fulltext_search_with_filters(self):
        """Full-text search works alongside tag/color filters."""
        tag = Tag.objects.create(user=self.user, name="work", color="#3b82f6")
        note1 = Note.objects.create(
            user=self.user, body="Deployment strategy for work", color="blue"
        )
        note1.tags.add(tag)
        Note.objects.create(
            user=self.user, body="Deployment strategy personal", color="green"
        )
        response = self.client.get(
            reverse("notes:note_list") + f"?q=deployment&tag={tag.id}"
        )
        notes = list(response.context["notes"])
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].color, "blue")


class NoteCreateViewTest(NoteViewTestMixin, TestCase):
    """Tests for creating notes."""

    def test_create_form_loads(self):
        """GET to create URL loads the form."""
        response = self.client.get(reverse("notes:note_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New Note")

    def test_create_note_post(self):
        """POST with valid data creates a note."""
        response = self.client.post(
            reverse("notes:note_create"),
            {"body": "Brand new note", "color": "default"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Note.objects.filter(body="Brand new note").exists())

    def test_create_sets_user(self):
        """Created note is owned by the request user."""
        self.client.post(
            reverse("notes:note_create"),
            {"body": "Owned note", "color": "default"},
        )
        note = Note.objects.get(body="Owned note")
        self.assertEqual(note.user, self.user)

    def test_create_with_tags(self):
        """Tags are saved correctly."""
        tag = Tag.objects.create(user=self.user, name="test-tag", color="#000")
        self.client.post(
            reverse("notes:note_create"),
            {"body": "Tagged", "color": "default", "tags": [tag.id]},
        )
        note = Note.objects.get(body="Tagged")
        self.assertIn(tag, note.tags.all())

    def test_create_without_title(self):
        """Title is optional."""
        self.client.post(
            reverse("notes:note_create"),
            {"body": "No title note", "color": "default"},
        )
        note = Note.objects.get(body="No title note")
        self.assertEqual(note.title, "")

    def test_create_empty_body_rejected(self):
        """Empty body is rejected."""
        response = self.client.post(
            reverse("notes:note_create"),
            {"body": "", "color": "default"},
        )
        self.assertEqual(response.status_code, 200)  # re-renders form
        self.assertEqual(Note.objects.count(), 0)


class NoteDetailViewTest(NoteViewTestMixin, TestCase):
    """Tests for viewing a note."""

    def test_detail_own_note(self):
        """User can view their own note."""
        note = Note.objects.create(user=self.user, body="Detail me")
        response = self.client.get(
            reverse("notes:note_detail", kwargs={"pk": note.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detail me")

    def test_detail_other_user_404(self):
        """Cannot view another user's note."""
        other = User.objects.create_user(
            email="other2@example.com", password="testpass123"
        )
        note = Note.objects.create(user=other, body="Private")
        response = self.client.get(
            reverse("notes:note_detail", kwargs={"pk": note.pk})
        )
        self.assertEqual(response.status_code, 404)


class NoteUpdateViewTest(NoteViewTestMixin, TestCase):
    """Tests for editing notes."""

    def test_update_note(self):
        """Can update note body."""
        note = Note.objects.create(user=self.user, body="Original")
        response = self.client.post(
            reverse("notes:note_update", kwargs={"pk": note.pk}),
            {"body": "Updated body", "color": "blue"},
        )
        self.assertEqual(response.status_code, 302)
        note.refresh_from_db()
        self.assertEqual(note.body, "Updated body")
        self.assertEqual(note.color, "blue")

    def test_update_other_user_404(self):
        """Cannot edit another user's note."""
        other = User.objects.create_user(
            email="other3@example.com", password="testpass123"
        )
        note = Note.objects.create(user=other, body="Private")
        response = self.client.post(
            reverse("notes:note_update", kwargs={"pk": note.pk}),
            {"body": "Hacked", "color": "default"},
        )
        self.assertEqual(response.status_code, 404)


class NoteDeleteViewTest(NoteViewTestMixin, TestCase):
    """Tests for deleting notes."""

    def test_soft_delete(self):
        """POST to delete URL soft-deletes the note."""
        note = Note.objects.create(user=self.user, body="Delete me")
        response = self.client.post(
            reverse("notes:note_delete", kwargs={"pk": note.pk})
        )
        self.assertEqual(response.status_code, 302)
        note.refresh_from_db()
        self.assertTrue(note.is_deleted)

    def test_delete_other_user_404(self):
        """Cannot delete another user's note."""
        other = User.objects.create_user(
            email="other4@example.com", password="testpass123"
        )
        note = Note.objects.create(user=other, body="Private")
        response = self.client.post(
            reverse("notes:note_delete", kwargs={"pk": note.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_deleted_note_not_in_list(self):
        """Soft-deleted note is hidden from list view."""
        note = Note.objects.create(user=self.user, body="Gone")
        note.soft_delete()
        response = self.client.get(reverse("notes:note_list"))
        self.assertNotContains(response, "Gone")


class NoteTogglePinViewTest(NoteViewTestMixin, TestCase):
    """Tests for pin toggle."""

    def test_toggle_pin_on(self):
        """Unpinned note becomes pinned."""
        note = Note.objects.create(
            user=self.user, body="Pin me", is_pinned=False
        )
        response = self.client.post(
            reverse("notes:note_toggle_pin", kwargs={"pk": note.pk})
        )
        self.assertEqual(response.status_code, 302)
        note.refresh_from_db()
        self.assertTrue(note.is_pinned)

    def test_toggle_pin_off(self):
        """Pinned note becomes unpinned."""
        note = Note.objects.create(
            user=self.user, body="Unpin me", is_pinned=True
        )
        response = self.client.post(
            reverse("notes:note_toggle_pin", kwargs={"pk": note.pk})
        )
        self.assertEqual(response.status_code, 302)
        note.refresh_from_db()
        self.assertFalse(note.is_pinned)
