"""
Tests for the Notes service layer (Phase 4A).
"""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from apps.core.models import Tag
from apps.notes.models import Note, NoteAttachment
from apps.notes.services import (
    get_note_detail,
    get_related_notes_for_entity,
    search_notes,
)

User = get_user_model()


class SearchNotesServiceTest(TestCase):
    """Tests for search_notes()."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="svc_user@example.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            email="svc_other@example.com", password="testpass123"
        )

    def test_user_isolation(self):
        """search_notes only returns notes belonging to the requesting user."""
        Note.objects.create(user=self.user, body="My secret note about alpha")
        Note.objects.create(user=self.other_user, body="Other secret note about alpha")
        result = search_notes(user=self.user, query="alpha")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["body"], "My secret note about alpha")

    def test_search_by_title(self):
        """Searching by title returns the note."""
        Note.objects.create(user=self.user, title="Kubernetes Strategy", body="Deploy")
        result = search_notes(user=self.user, query="kubernetes")
        self.assertEqual(result["count"], 1)
        self.assertIn("title", result["results"][0]["match"]["matched_in"])

    def test_search_by_body(self):
        """Searching by body returns the note."""
        Note.objects.create(user=self.user, body="Deployment pipeline automation")
        result = search_notes(user=self.user, query="automation")
        self.assertEqual(result["count"], 1)
        self.assertIn("body", result["results"][0]["match"]["matched_in"])

    def test_search_by_tag_name(self):
        """Searching by tag name returns a note tagged with it."""
        note = Note.objects.create(user=self.user, body="General thoughts")
        tag = Tag.objects.create(user=self.user, name="devotional", color="#3b82f6")
        note.tags.add(tag)
        result = search_notes(user=self.user, query="devotional")
        self.assertEqual(result["count"], 1)
        self.assertIn("tags", result["results"][0]["match"]["matched_in"])

    def test_search_by_attachment_text(self):
        """Searching by attachment display text returns the note."""
        from apps.life.models import Project

        project = Project.objects.create(
            user=self.user, title="Morning routine refinement", description="P"
        )
        note = Note.objects.create(user=self.user, body="General thoughts")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)
        result = search_notes(user=self.user, query="morning routine")
        self.assertEqual(result["count"], 1)
        self.assertIn("attachments", result["results"][0]["match"]["matched_in"])

    def test_matched_in_labels_multiple_sources(self):
        """matched_in contains all fields that match the query."""
        note = Note.objects.create(
            user=self.user,
            title="Devotional morning reflections",
            body="Devotional thoughts for the morning",
        )
        tag = Tag.objects.create(user=self.user, name="devotional", color="#3b82f6")
        note.tags.add(tag)
        result = search_notes(user=self.user, query="devotional")
        matched_in = result["results"][0]["match"]["matched_in"]
        self.assertIn("title", matched_in)
        self.assertIn("body", matched_in)
        self.assertIn("tags", matched_in)

    def test_ranking_title_above_body(self):
        """Title matches rank above body-only matches."""
        Note.objects.create(
            user=self.user, title="Kubernetes", body="General deployment notes"
        )
        Note.objects.create(
            user=self.user, title="General notes", body="Kubernetes options discussed"
        )
        result = search_notes(user=self.user, query="kubernetes")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["results"][0]["display_title"], "Kubernetes")

    def test_ranking_title_above_tags(self):
        """Title matches rank above tag-only matches."""
        note1 = Note.objects.create(
            user=self.user, title="Devotional thoughts", body="Reflections"
        )
        note2 = Note.objects.create(user=self.user, body="General notes")
        tag = Tag.objects.create(user=self.user, name="devotional", color="#000")
        note2.tags.add(tag)
        result = search_notes(user=self.user, query="devotional")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["results"][0]["note_id"], note1.pk)

    def test_soft_deleted_excluded(self):
        """Soft-deleted notes are not returned."""
        note = Note.objects.create(user=self.user, body="Will be deleted alpha")
        note.soft_delete()
        result = search_notes(user=self.user, query="alpha")
        self.assertEqual(result["count"], 0)

    def test_filter_by_tag_ids(self):
        """tag_ids filter restricts results."""
        tag = Tag.objects.create(user=self.user, name="work", color="#000")
        note1 = Note.objects.create(user=self.user, body="Work note")
        note1.tags.add(tag)
        Note.objects.create(user=self.user, body="Personal note")
        result = search_notes(user=self.user, query=None, tag_ids=[tag.id])
        self.assertEqual(result["count"], 1)
        self.assertIn("work", result["results"][0]["tag_names"])

    def test_filter_by_color(self):
        """color filter restricts results."""
        Note.objects.create(user=self.user, body="Red note", color="red")
        Note.objects.create(user=self.user, body="Blue note", color="blue")
        result = search_notes(user=self.user, query=None, color="red")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["color"], "red")

    def test_filter_by_pinned(self):
        """pinned filter restricts results."""
        Note.objects.create(user=self.user, body="Pinned", is_pinned=True)
        Note.objects.create(user=self.user, body="Unpinned", is_pinned=False)
        result = search_notes(user=self.user, query=None, pinned=True)
        self.assertEqual(result["count"], 1)
        self.assertTrue(result["results"][0]["is_pinned"])

    def test_filter_by_date_range(self):
        """date_from and date_to restrict results."""
        from datetime import date

        note = Note.objects.create(user=self.user, body="Dated note")
        # The note was just created, so created_at is today
        today = date.today()
        result = search_notes(user=self.user, query=None, date_from=today, date_to=today)
        self.assertEqual(result["count"], 1)

    def test_filter_attached_only(self):
        """attached_only filter only returns notes with attachments."""
        from apps.life.models import Project

        project = Project.objects.create(
            user=self.user, title="P1", description="P"
        )
        note_attached = Note.objects.create(user=self.user, body="Attached note")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(
            note=note_attached, content_type=ct, object_id=project.pk
        )
        Note.objects.create(user=self.user, body="Standalone note")
        result = search_notes(user=self.user, query=None, attached_only=True)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["note_id"], note_attached.pk)

    def test_pagination_limit_offset(self):
        """limit and offset paginate results."""
        for i in range(5):
            Note.objects.create(user=self.user, body=f"Note {i}")
        result_page1 = search_notes(user=self.user, query=None, limit=2, offset=0)
        result_page2 = search_notes(user=self.user, query=None, limit=2, offset=2)
        self.assertEqual(result_page1["count"], 5)
        self.assertEqual(len(result_page1["results"]), 2)
        self.assertEqual(len(result_page2["results"]), 2)
        # Pages should have different notes
        ids_1 = {r["note_id"] for r in result_page1["results"]}
        ids_2 = {r["note_id"] for r in result_page2["results"]}
        self.assertEqual(len(ids_1 & ids_2), 0)

    def test_no_query_returns_all(self):
        """Without a query, all user notes are returned."""
        Note.objects.create(user=self.user, body="Note A")
        Note.objects.create(user=self.user, body="Note B")
        result = search_notes(user=self.user, query=None)
        self.assertEqual(result["count"], 2)

    def test_citation_block_structure(self):
        """Citation block contains all required fields."""
        note = Note.objects.create(
            user=self.user, title="Test", body="Body content", color="blue"
        )
        result = search_notes(user=self.user, query="test")
        block = result["results"][0]
        required_keys = {
            "note_id", "display_title", "body_preview", "body",
            "created_at", "updated_at", "is_pinned", "color",
            "tag_names", "attachment_count", "attachments", "url", "match",
        }
        self.assertTrue(required_keys.issubset(block.keys()))
        match_keys = {"query", "matched_in", "headline", "rank"}
        self.assertTrue(match_keys.issubset(block["match"].keys()))

    def test_headline_included_on_search(self):
        """headline is populated when searching."""
        Note.objects.create(user=self.user, body="The kubernetes deployment was successful")
        result = search_notes(user=self.user, query="kubernetes")
        self.assertTrue(result["results"][0]["match"]["headline"])

    def test_rank_included_on_search(self):
        """rank is a float when searching."""
        Note.objects.create(user=self.user, body="Unique xyzzyword content")
        result = search_notes(user=self.user, query="xyzzyword")
        self.assertIsInstance(result["results"][0]["match"]["rank"], float)

    def test_attachment_block_structure(self):
        """Attachment blocks contain required fields with URL resolution."""
        from apps.life.models import Project

        project = Project.objects.create(
            user=self.user, title="URL Project", description="P"
        )
        note = Note.objects.create(user=self.user, body="With attachment")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)
        result = search_notes(user=self.user, query=None)
        att = result["results"][0]["attachments"][0]
        self.assertEqual(att["content_type"], "life.project")
        self.assertEqual(att["object_id"], project.pk)
        self.assertIn("URL Project", att["display"])
        # Project has get_absolute_url, so url should be set
        self.assertIsNotNone(att["url"])


class GetNoteDetailServiceTest(TestCase):
    """Tests for get_note_detail()."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="detail_user@example.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            email="detail_other@example.com", password="testpass123"
        )

    def test_returns_own_note(self):
        """get_note_detail returns the user's note."""
        note = Note.objects.create(user=self.user, title="My Note", body="Content")
        result = get_note_detail(user=self.user, note_id=note.pk)
        self.assertIsNotNone(result)
        self.assertEqual(result["note_id"], note.pk)
        self.assertEqual(result["body"], "Content")

    def test_other_user_returns_none(self):
        """get_note_detail returns None for another user's note."""
        note = Note.objects.create(user=self.other_user, body="Private")
        result = get_note_detail(user=self.user, note_id=note.pk)
        self.assertIsNone(result)

    def test_soft_deleted_returns_none(self):
        """get_note_detail returns None for soft-deleted notes."""
        note = Note.objects.create(user=self.user, body="Deleted note")
        note.soft_delete()
        result = get_note_detail(user=self.user, note_id=note.pk)
        self.assertIsNone(result)

    def test_nonexistent_returns_none(self):
        """get_note_detail returns None for non-existent note ID."""
        result = get_note_detail(user=self.user, note_id=999999)
        self.assertIsNone(result)

    def test_includes_tags_and_attachments(self):
        """get_note_detail includes tags and attachments."""
        from apps.life.models import Project

        note = Note.objects.create(user=self.user, body="Detail test")
        tag = Tag.objects.create(user=self.user, name="testtag", color="#000")
        note.tags.add(tag)
        project = Project.objects.create(
            user=self.user, title="Detail Project", description="P"
        )
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)
        result = get_note_detail(user=self.user, note_id=note.pk)
        self.assertIn("testtag", result["tag_names"])
        self.assertEqual(result["attachment_count"], 1)
        self.assertIn("Detail Project", result["attachments"][0]["display"])


class GetRelatedNotesServiceTest(TestCase):
    """Tests for get_related_notes_for_entity()."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="related_user@example.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            email="related_other@example.com", password="testpass123"
        )

    def _create_project(self, user=None, title="Test Project"):
        from apps.life.models import Project

        return Project.objects.create(
            user=user or self.user, title=title, description="P"
        )

    def test_returns_notes_for_entity(self):
        """Returns notes attached to the specified entity."""
        project = self._create_project()
        note = Note.objects.create(user=self.user, body="Attached note")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)
        results = get_related_notes_for_entity(
            user=self.user, content_type="life.project", object_id=project.pk
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["note_id"], note.pk)

    def test_user_isolation(self):
        """Does not return another user's notes attached to the same entity."""
        project = self._create_project()
        ct = ContentType.objects.get_for_model(project)
        my_note = Note.objects.create(user=self.user, body="My note")
        NoteAttachment.objects.create(note=my_note, content_type=ct, object_id=project.pk)
        other_note = Note.objects.create(user=self.other_user, body="Other note")
        NoteAttachment.objects.create(
            note=other_note, content_type=ct, object_id=project.pk
        )
        results = get_related_notes_for_entity(
            user=self.user, content_type="life.project", object_id=project.pk
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["note_id"], my_note.pk)

    def test_excludes_soft_deleted(self):
        """Soft-deleted notes are not returned."""
        project = self._create_project()
        note = Note.objects.create(user=self.user, body="Deleted note")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)
        note.soft_delete()
        results = get_related_notes_for_entity(
            user=self.user, content_type="life.project", object_id=project.pk
        )
        self.assertEqual(len(results), 0)

    def test_invalid_content_type_returns_empty(self):
        """Invalid content_type string returns empty list."""
        results = get_related_notes_for_entity(
            user=self.user, content_type="nonexistent.model", object_id=1
        )
        self.assertEqual(len(results), 0)

    def test_no_attachments_returns_empty(self):
        """Entity with no attached notes returns empty list."""
        project = self._create_project()
        results = get_related_notes_for_entity(
            user=self.user, content_type="life.project", object_id=project.pk
        )
        self.assertEqual(len(results), 0)

    def test_multiple_notes_per_entity(self):
        """Returns all notes attached to the entity."""
        project = self._create_project()
        ct = ContentType.objects.get_for_model(project)
        n1 = Note.objects.create(user=self.user, body="Note 1")
        n2 = Note.objects.create(user=self.user, body="Note 2")
        NoteAttachment.objects.create(note=n1, content_type=ct, object_id=project.pk)
        NoteAttachment.objects.create(note=n2, content_type=ct, object_id=project.pk)
        results = get_related_notes_for_entity(
            user=self.user, content_type="life.project", object_id=project.pk
        )
        self.assertEqual(len(results), 2)
