"""
Tests for the refresh_note_attachments_index management command
and entity rename signals (Phase 4B.1).
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from unittest import skipUnless

from django.test import TestCase

from apps.notes.utils import is_postgres

try:
    from django.contrib.postgres.search import SearchQuery
except ImportError:
    SearchQuery = None

from apps.core.models import Tag
from apps.notes.models import Note, NoteAttachment
from apps.notes.services import (
    refresh_notes_for_content_type,
    refresh_notes_for_entity,
    refresh_notes_with_attachments,
)

User = get_user_model()


class RefreshCommandTest(TestCase):
    """Tests for the refresh_note_attachments_index management command."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="refresh_cmd@example.com", password="testpass123"
        )

    def _create_project(self, title="Original Project"):
        from apps.life.models import Project

        return Project.objects.create(
            user=self.user, title=title, description="A project"
        )

    def _attach_note_to_project(self, note, project):
        ct = ContentType.objects.get_for_model(project)
        return NoteAttachment.objects.create(
            note=note, content_type=ct, object_id=project.pk
        )

    @skipUnless(is_postgres(), "Requires PostgreSQL full-text search")
    def test_command_refreshes_after_entity_rename(self):
        """Rename entity, run command, confirm attachments_text and search updated."""
        from apps.life.models import Project

        project = self._create_project("Morning Routine Alpha")
        note = Note.objects.create(user=self.user, body="General thoughts")
        self._attach_note_to_project(note, project)
        note.refresh_from_db()
        self.assertIn("Morning Routine Alpha", note.attachments_text)

        # Rename the project via queryset update (bypasses signals)
        Project.objects.filter(pk=project.pk).update(title="Evening Routine Beta")

        # attachments_text is still stale
        note.refresh_from_db()
        self.assertIn("Morning Routine Alpha", note.attachments_text)

        # Run the command targeting this specific entity
        out = StringIO()
        call_command(
            "refresh_note_attachments_index",
            content_type="life.project",
            object_id=project.pk,
            stdout=out,
        )

        # Confirm updated
        note.refresh_from_db()
        self.assertIn("Evening Routine Beta", note.attachments_text)
        self.assertNotIn("Morning Routine Alpha", note.attachments_text)

        # Search finds new name
        found = Note.objects.filter(
            user=self.user, search_vector=SearchQuery("Evening")
        )
        self.assertEqual(found.count(), 1)

    def test_command_dry_run_does_not_update(self):
        """--dry-run prints counts but does not change data."""
        from apps.life.models import Project

        project = self._create_project("DryRun Project")
        note = Note.objects.create(user=self.user, body="Dry run test")
        self._attach_note_to_project(note, project)
        note.refresh_from_db()
        original_text = note.attachments_text

        # Rename via queryset
        Project.objects.filter(pk=project.pk).update(title="Renamed DryRun")

        # Run with --dry-run
        out = StringIO()
        call_command(
            "refresh_note_attachments_index",
            content_type="life.project",
            object_id=project.pk,
            dry_run=True,
            stdout=out,
        )

        # Should NOT have updated
        note.refresh_from_db()
        self.assertEqual(note.attachments_text, original_text)
        self.assertIn("DRY RUN", out.getvalue())

    def test_command_all_scope(self):
        """Running without scope refreshes all attached notes."""
        project = self._create_project("AllScope Project")
        note = Note.objects.create(user=self.user, body="All scope test")
        self._attach_note_to_project(note, project)

        out = StringIO()
        call_command("refresh_note_attachments_index", stdout=out)
        output = out.getvalue()
        self.assertIn("Notes considered: 1", output)
        self.assertIn("Refresh complete", output)

    def test_command_content_type_scope(self):
        """--content-type without --object-id refreshes all notes for that type."""
        from apps.life.models import Project

        p1 = self._create_project("Project CT1")
        p2 = self._create_project("Project CT2")
        n1 = Note.objects.create(user=self.user, body="Note CT1")
        n2 = Note.objects.create(user=self.user, body="Note CT2")
        self._attach_note_to_project(n1, p1)
        self._attach_note_to_project(n2, p2)

        out = StringIO()
        call_command(
            "refresh_note_attachments_index",
            content_type="life.project",
            stdout=out,
        )
        self.assertIn("Notes considered: 2", out.getvalue())

    def test_command_object_id_requires_content_type(self):
        """--object-id without --content-type prints error."""
        out = StringIO()
        err = StringIO()
        call_command(
            "refresh_note_attachments_index",
            object_id=1,
            stdout=out,
            stderr=err,
        )
        self.assertIn("--object-id requires --content-type", err.getvalue())

    def test_command_verbose_output(self):
        """--verbose produces extra scope output."""
        out = StringIO()
        call_command(
            "refresh_note_attachments_index",
            verbose=True,
            stdout=out,
        )
        self.assertIn("Scope:", out.getvalue())


class RefreshServiceHelpersTest(TestCase):
    """Tests for the refresh service helper functions."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="refresh_svc@example.com", password="testpass123"
        )

    def _create_project(self, title="Test Project"):
        from apps.life.models import Project

        return Project.objects.create(
            user=self.user, title=title, description="P"
        )

    def test_refresh_notes_for_entity(self):
        """refresh_notes_for_entity refreshes the correct notes."""
        project = self._create_project("Entity Refresh Project")
        note = Note.objects.create(user=self.user, body="Entity test")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)

        result = refresh_notes_for_entity(
            content_type_str="life.project", object_id=project.pk
        )
        self.assertEqual(result["notes_considered"], 1)

    def test_refresh_notes_for_entity_invalid_ct(self):
        """Invalid content type returns zero counts."""
        result = refresh_notes_for_entity(
            content_type_str="fake.model", object_id=1
        )
        self.assertEqual(result["notes_considered"], 0)

    def test_refresh_notes_with_attachments(self):
        """refresh_notes_with_attachments processes all attached notes."""
        project = self._create_project()
        n1 = Note.objects.create(user=self.user, body="Attached 1")
        n2 = Note.objects.create(user=self.user, body="Standalone")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=n1, content_type=ct, object_id=project.pk)

        result = refresh_notes_with_attachments()
        self.assertEqual(result["notes_considered"], 1)

    def test_refresh_notes_for_content_type(self):
        """refresh_notes_for_content_type processes notes for that type."""
        project = self._create_project()
        note = Note.objects.create(user=self.user, body="CT test")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)

        result = refresh_notes_for_content_type(content_type_str="life.project")
        self.assertEqual(result["notes_considered"], 1)

    def test_dry_run_does_not_write(self):
        """dry_run=True returns counts but writes nothing."""
        from apps.life.models import Project

        project = self._create_project("DryRun Svc")
        note = Note.objects.create(user=self.user, body="Svc dry run")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)
        note.refresh_from_db()
        original = note.attachments_text

        # Rename via queryset
        Project.objects.filter(pk=project.pk).update(title="Renamed Svc")

        result = refresh_notes_for_entity(
            content_type_str="life.project", object_id=project.pk, dry_run=True
        )
        self.assertEqual(result["notes_considered"], 1)
        self.assertEqual(result["notes_updated"], 0)

        # Verify not updated
        note.refresh_from_db()
        self.assertEqual(note.attachments_text, original)


class EntityRenameSignalTest(TestCase):
    """Tests for Layer 2 entity rename signals (Phase 4B.1)."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="rename_signal@example.com", password="testpass123"
        )

    @skipUnless(is_postgres(), "Requires PostgreSQL full-text search")
    def test_project_rename_auto_refreshes_notes(self):
        """Renaming a Project via save() auto-refreshes attached note index."""
        from apps.life.models import Project

        project = Project.objects.create(
            user=self.user, title="Alpha Project", description="P"
        )
        note = Note.objects.create(user=self.user, body="Signal test note")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)

        note.refresh_from_db()
        self.assertIn("Alpha Project", note.attachments_text)

        # Rename via model save() (triggers signals)
        project.title = "Beta Project"
        project.save()

        note.refresh_from_db()
        self.assertIn("Beta Project", note.attachments_text)
        self.assertNotIn("Alpha Project", note.attachments_text)

        # Search finds new name
        found = Note.objects.filter(
            user=self.user, search_vector=SearchQuery("Beta")
        )
        self.assertEqual(found.count(), 1)

    def test_task_rename_auto_refreshes_notes(self):
        """Renaming a Task via save() auto-refreshes attached note index."""
        from apps.life.models import Task

        task = Task.objects.create(
            user=self.user, title="Original Task Title"
        )
        note = Note.objects.create(user=self.user, body="Task signal test")
        ct = ContentType.objects.get_for_model(task)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=task.pk)

        note.refresh_from_db()
        self.assertIn("Original Task Title", note.attachments_text)

        task.title = "Updated Task Title"
        task.save()

        note.refresh_from_db()
        self.assertIn("Updated Task Title", note.attachments_text)

    def test_no_rename_no_refresh(self):
        """Saving an entity without changing title does NOT trigger refresh."""
        from apps.life.models import Project

        project = Project.objects.create(
            user=self.user, title="Stable Project", description="P"
        )
        note = Note.objects.create(user=self.user, body="No rename test")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)

        note.refresh_from_db()
        original_text = note.attachments_text

        # Save without changing title
        project.description = "Updated description"
        project.save()

        note.refresh_from_db()
        self.assertEqual(note.attachments_text, original_text)

    def test_new_entity_does_not_trigger_rename(self):
        """Creating a new entity does NOT trigger rename refresh."""
        from apps.life.models import Project

        # This should not raise or produce errors
        Project.objects.create(
            user=self.user, title="Brand New Project", description="P"
        )
        # If we get here without error, the signal correctly skipped new instances
