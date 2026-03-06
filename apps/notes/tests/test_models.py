"""
Tests for the Note and NoteAttachment models.
"""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from unittest import skipUnless

from django.test import TestCase

from apps.notes.utils import is_postgres

try:
    from django.contrib.postgres.search import SearchQuery
except ImportError:
    SearchQuery = None

from apps.core.models import Tag
from apps.notes.models import Note, NoteAttachment

User = get_user_model()


class NoteModelTest(TestCase):
    """Tests for the Note model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="noteuser@example.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            email="other@example.com", password="testpass123"
        )

    def test_create_note(self):
        """Can create a note with required fields."""
        note = Note.objects.create(user=self.user, body="Test note body")
        self.assertEqual(note.body, "Test note body")
        self.assertEqual(note.user, self.user)
        self.assertEqual(note.status, "active")

    def test_create_note_with_title(self):
        """Can create a note with an explicit title."""
        note = Note.objects.create(
            user=self.user, title="My Title", body="Some body"
        )
        self.assertEqual(note.title, "My Title")

    def test_str_with_title(self):
        """__str__ returns title when set."""
        note = Note.objects.create(
            user=self.user, title="Quick Thought", body="Details here"
        )
        self.assertEqual(str(note), "Quick Thought")

    def test_str_without_title(self):
        """__str__ returns body_preview when title is blank."""
        note = Note.objects.create(user=self.user, body="A short body")
        self.assertEqual(str(note), "A short body")

    def test_body_preview_short(self):
        """body_preview returns full body when under 100 chars."""
        note = Note.objects.create(user=self.user, body="Short text")
        self.assertEqual(note.body_preview, "Short text")

    def test_body_preview_long(self):
        """body_preview truncates at ~100 chars with word boundary."""
        long_text = "word " * 30  # 150 chars
        note = Note.objects.create(user=self.user, body=long_text)
        self.assertTrue(len(note.body_preview) <= 105)
        self.assertTrue(note.body_preview.endswith("..."))

    def test_body_preview_empty(self):
        """body_preview returns 'Empty note' for empty body."""
        note = Note(user=self.user, body="")
        self.assertEqual(note.body_preview, "Empty note")

    def test_display_title_with_title(self):
        """display_title returns title when set."""
        note = Note(user=self.user, title="Title", body="Body")
        self.assertEqual(note.display_title, "Title")

    def test_display_title_without_title(self):
        """display_title returns body_preview when title is blank."""
        note = Note(user=self.user, title="", body="Body text here")
        self.assertEqual(note.display_title, "Body text here")

    def test_word_count_computed_on_save(self):
        """word_count is auto-calculated on save."""
        note = Note.objects.create(
            user=self.user, body="one two three four five"
        )
        self.assertEqual(note.word_count, 5)

    def test_word_count_empty_body(self):
        """word_count is 0 for empty body."""
        note = Note(user=self.user, body="")
        note.save()
        self.assertEqual(note.word_count, 0)

    def test_default_ordering_pinned_first(self):
        """Pinned notes appear before unpinned in default ordering."""
        unpinned = Note.objects.create(
            user=self.user, body="Unpinned", is_pinned=False
        )
        pinned = Note.objects.create(
            user=self.user, body="Pinned", is_pinned=True
        )
        notes = list(Note.objects.filter(user=self.user))
        self.assertEqual(notes[0], pinned)

    def test_soft_delete(self):
        """Soft delete hides note from default manager."""
        note = Note.objects.create(user=self.user, body="Will be deleted")
        note.soft_delete()
        self.assertTrue(note.is_deleted)
        self.assertNotIn(note, Note.objects.filter(user=self.user))
        self.assertIn(note, Note.all_objects.filter(user=self.user))

    def test_tag_m2m(self):
        """Tags can be assigned to notes."""
        tag = Tag.objects.create(user=self.user, name="idea", color="#3b82f6")
        note = Note.objects.create(user=self.user, body="Tagged note")
        note.tags.add(tag)
        self.assertIn(tag, note.tags.all())

    def test_color_default(self):
        """Default color is 'default'."""
        note = Note.objects.create(user=self.user, body="Test")
        self.assertEqual(note.color, "default")

    def test_get_absolute_url(self):
        """get_absolute_url returns correct path."""
        note = Note.objects.create(user=self.user, body="Test")
        self.assertEqual(note.get_absolute_url(), f"/notes/{note.pk}/")

    def test_user_isolation(self):
        """Default manager only returns notes for the queried user."""
        Note.objects.create(user=self.user, body="My note")
        Note.objects.create(user=self.other_user, body="Their note")
        my_notes = Note.objects.filter(user=self.user)
        self.assertEqual(my_notes.count(), 1)
        self.assertEqual(my_notes.first().body, "My note")

    @skipUnless(is_postgres(), "Requires PostgreSQL full-text search")
    def test_search_vector_populated_on_save(self):
        """search_vector is populated after save."""
        note = Note.objects.create(
            user=self.user, title="DevOps Strategy", body="Kubernetes deployment plan"
        )
        note.refresh_from_db()
        self.assertIsNotNone(note.search_vector)

    @skipUnless(is_postgres(), "Requires PostgreSQL full-text search")
    def test_search_vector_updates_on_edit(self):
        """search_vector updates when note body changes."""
        note = Note.objects.create(user=self.user, body="Original content alpha")
        note.body = "Updated content beta"
        note.save()
        note.refresh_from_db()
        # Search for the new content should work
        from django.contrib.postgres.search import SearchQuery

        found = Note.objects.filter(
            user=self.user, search_vector=SearchQuery("beta")
        )
        self.assertEqual(found.count(), 1)
        # Old content should not match
        not_found = Note.objects.filter(
            user=self.user, search_vector=SearchQuery("alpha")
        )
        self.assertEqual(not_found.count(), 0)

    @skipUnless(is_postgres(), "Requires PostgreSQL full-text search")
    def test_search_vector_title_weighted_higher(self):
        """Notes matching in title rank higher than body-only matches."""
        from django.contrib.postgres.search import SearchQuery, SearchRank
        from django.db.models import F

        Note.objects.create(
            user=self.user,
            title="Kubernetes",
            body="Some general deployment notes",
        )
        Note.objects.create(
            user=self.user,
            title="General notes",
            body="We discussed Kubernetes options",
        )
        query = SearchQuery("kubernetes")
        results = (
            Note.objects.filter(user=self.user, search_vector=query)
            .annotate(rank=SearchRank(F("search_vector"), query))
            .order_by("-rank")
        )
        self.assertEqual(results.count(), 2)
        # Title match should rank higher
        self.assertEqual(results.first().title, "Kubernetes")


class NoteAttachmentModelTest(TestCase):
    """Tests for the NoteAttachment model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="noteuser@example.com", password="testpass123"
        )
        self.note = Note.objects.create(user=self.user, body="Test note")

    def _create_project(self):
        """Helper to create a Project for attachment tests."""
        from apps.life.models import Project

        return Project.objects.create(
            user=self.user, title="Test Project", description="A project"
        )

    def test_attach_to_project(self):
        """Can attach a note to a Project."""
        project = self._create_project()
        ct = ContentType.objects.get_for_model(project)
        att = NoteAttachment.objects.create(
            note=self.note, content_type=ct, object_id=project.pk
        )
        self.assertEqual(att.attached_entity, project)

    def test_unique_constraint(self):
        """Cannot attach same note to same entity twice."""
        project = self._create_project()
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(
            note=self.note, content_type=ct, object_id=project.pk
        )
        with self.assertRaises(IntegrityError):
            NoteAttachment.objects.create(
                note=self.note, content_type=ct, object_id=project.pk
            )

    def test_note_cascade_delete(self):
        """Deleting a note hard-deletes its attachments."""
        project = self._create_project()
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(
            note=self.note, content_type=ct, object_id=project.pk
        )
        # Hard delete the note (bypass soft delete for this test)
        note_pk = self.note.pk
        Note.all_objects.filter(pk=note_pk).delete()
        self.assertEqual(NoteAttachment.objects.count(), 0)

    def test_attachment_count_property(self):
        """Note.attachment_count returns correct count."""
        self.assertEqual(self.note.attachment_count, 0)
        project = self._create_project()
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(
            note=self.note, content_type=ct, object_id=project.pk
        )
        self.assertEqual(self.note.attachment_count, 1)

    def test_multiple_attachments_per_note(self):
        """A note can have multiple attachments to different entities."""
        from apps.life.models import Project

        p1 = Project.objects.create(
            user=self.user, title="Project 1", description="P1"
        )
        p2 = Project.objects.create(
            user=self.user, title="Project 2", description="P2"
        )
        ct = ContentType.objects.get_for_model(p1)
        NoteAttachment.objects.create(
            note=self.note, content_type=ct, object_id=p1.pk
        )
        NoteAttachment.objects.create(
            note=self.note, content_type=ct, object_id=p2.pk
        )
        self.assertEqual(self.note.attachment_count, 2)

    def test_multiple_notes_per_entity(self):
        """An entity can have multiple notes attached."""
        project = self._create_project()
        ct = ContentType.objects.get_for_model(project)
        note2 = Note.objects.create(user=self.user, body="Second note")
        NoteAttachment.objects.create(
            note=self.note, content_type=ct, object_id=project.pk
        )
        NoteAttachment.objects.create(
            note=note2, content_type=ct, object_id=project.pk
        )
        attachments = NoteAttachment.objects.filter(
            content_type=ct, object_id=project.pk
        )
        self.assertEqual(attachments.count(), 2)


class NoteSearchIndexTest(TestCase):
    """Tests for Phase 3 denormalized search index (tags_text, attachments_text)."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="searchindex@example.com", password="testpass123"
        )

    def _create_project(self, title="Test Project"):
        from apps.life.models import Project

        return Project.objects.create(
            user=self.user, title=title, description="A project"
        )

    def test_tags_text_populated_on_tag_add(self):
        """Adding a tag updates tags_text."""
        note = Note.objects.create(user=self.user, body="Some note")
        tag = Tag.objects.create(user=self.user, name="devotional", color="#3b82f6")
        note.tags.add(tag)
        note.refresh_from_db()
        self.assertEqual(note.tags_text, "devotional")

    def test_tags_text_multiple_tags(self):
        """Multiple tags appear in tags_text."""
        note = Note.objects.create(user=self.user, body="Some note")
        t1 = Tag.objects.create(user=self.user, name="alpha", color="#000")
        t2 = Tag.objects.create(user=self.user, name="beta", color="#111")
        note.tags.add(t1, t2)
        note.refresh_from_db()
        self.assertIn("alpha", note.tags_text)
        self.assertIn("beta", note.tags_text)

    def test_tags_text_cleared_on_tag_remove(self):
        """Removing a tag updates tags_text."""
        note = Note.objects.create(user=self.user, body="Some note")
        tag = Tag.objects.create(user=self.user, name="removeme", color="#000")
        note.tags.add(tag)
        note.refresh_from_db()
        self.assertIn("removeme", note.tags_text)
        note.tags.remove(tag)
        note.refresh_from_db()
        self.assertEqual(note.tags_text, "")

    def test_tags_text_cleared_on_tags_clear(self):
        """Clearing all tags updates tags_text."""
        note = Note.objects.create(user=self.user, body="Some note")
        tag = Tag.objects.create(user=self.user, name="clearme", color="#000")
        note.tags.add(tag)
        note.tags.clear()
        note.refresh_from_db()
        self.assertEqual(note.tags_text, "")

    @skipUnless(is_postgres(), "Requires PostgreSQL full-text search")
    def test_search_vector_includes_tag_names(self):
        """Search vector matches tag names after tag add."""
        note = Note.objects.create(user=self.user, body="General thoughts")
        tag = Tag.objects.create(user=self.user, name="devotional", color="#3b82f6")
        note.tags.add(tag)
        found = Note.objects.filter(
            user=self.user, search_vector=SearchQuery("devotional")
        )
        self.assertEqual(found.count(), 1)
        self.assertEqual(found.first().pk, note.pk)

    @skipUnless(is_postgres(), "Requires PostgreSQL full-text search")
    def test_search_vector_excludes_removed_tag(self):
        """After removing a tag, search no longer matches it."""
        note = Note.objects.create(user=self.user, body="General thoughts")
        tag = Tag.objects.create(user=self.user, name="xyzuniquetag", color="#000")
        note.tags.add(tag)
        self.assertEqual(
            Note.objects.filter(
                user=self.user, search_vector=SearchQuery("xyzuniquetag")
            ).count(),
            1,
        )
        note.tags.remove(tag)
        self.assertEqual(
            Note.objects.filter(
                user=self.user, search_vector=SearchQuery("xyzuniquetag")
            ).count(),
            0,
        )

    def test_attachments_text_populated_on_attachment_create(self):
        """Creating a NoteAttachment updates attachments_text."""
        project = self._create_project("Morning routine refinement")
        note = Note.objects.create(user=self.user, body="Some note")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(
            note=note, content_type=ct, object_id=project.pk
        )
        note.refresh_from_db()
        self.assertIn("Morning routine refinement", note.attachments_text)
        self.assertIn("Project", note.attachments_text)

    def test_attachments_text_cleared_on_attachment_delete(self):
        """Deleting a NoteAttachment updates attachments_text."""
        project = self._create_project("Temp project")
        note = Note.objects.create(user=self.user, body="Some note")
        ct = ContentType.objects.get_for_model(project)
        att = NoteAttachment.objects.create(
            note=note, content_type=ct, object_id=project.pk
        )
        note.refresh_from_db()
        self.assertIn("Temp project", note.attachments_text)
        att.delete()
        note.refresh_from_db()
        self.assertEqual(note.attachments_text, "")

    @skipUnless(is_postgres(), "Requires PostgreSQL full-text search")
    def test_search_vector_includes_attachment_text(self):
        """Search vector matches attachment display string."""
        project = self._create_project("Morning routine refinement")
        note = Note.objects.create(user=self.user, body="General thoughts")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(
            note=note, content_type=ct, object_id=project.pk
        )
        found = Note.objects.filter(
            user=self.user, search_vector=SearchQuery("routine refinement")
        )
        self.assertEqual(found.count(), 1)
        self.assertEqual(found.first().pk, note.pk)

    @skipUnless(is_postgres(), "Requires PostgreSQL full-text search")
    def test_search_vector_excludes_deleted_attachment(self):
        """After deleting attachment, search no longer matches its text."""
        project = self._create_project("Zzzyyyxxx unique project")
        note = Note.objects.create(user=self.user, body="General thoughts")
        ct = ContentType.objects.get_for_model(project)
        att = NoteAttachment.objects.create(
            note=note, content_type=ct, object_id=project.pk
        )
        self.assertEqual(
            Note.objects.filter(
                user=self.user, search_vector=SearchQuery("Zzzyyyxxx")
            ).count(),
            1,
        )
        att.delete()
        self.assertEqual(
            Note.objects.filter(
                user=self.user, search_vector=SearchQuery("Zzzyyyxxx")
            ).count(),
            0,
        )

    def test_attachment_display_method(self):
        """NoteAttachment.attachment_display() returns expected format."""
        project = self._create_project("My Test Project")
        note = Note.objects.create(user=self.user, body="Some note")
        ct = ContentType.objects.get_for_model(project)
        att = NoteAttachment.objects.create(
            note=note, content_type=ct, object_id=project.pk
        )
        display = att.attachment_display()
        self.assertIn("Project", display)
        self.assertIn("My Test Project", display)

    def test_rebuild_tags_text_idempotent(self):
        """rebuild_tags_text produces consistent results on repeated calls."""
        note = Note.objects.create(user=self.user, body="Some note")
        tag = Tag.objects.create(user=self.user, name="testag", color="#000")
        note.tags.add(tag)
        note.refresh_from_db()
        first = note.tags_text
        note.rebuild_tags_text()
        note.refresh_from_db()
        self.assertEqual(note.tags_text, first)
