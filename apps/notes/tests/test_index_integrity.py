"""
Tests for Phase 4B.2: Index integrity, registry, and observability.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TestCase

from apps.notes.index_registry import NOTE_INDEX_REGISTRY
from apps.notes.models import Note, NoteAttachment
from apps.notes.services import (
    find_notes_missing_attachments_text,
    find_notes_missing_search_vector,
    get_note_index_integrity_report,
    repair_notes_missing_index,
)

User = get_user_model()


class IndexRegistryTest(TestCase):
    """Tests for the NOTE_INDEX_REGISTRY configuration."""

    def test_registry_contains_expected_models(self):
        """Registry includes all 5 whitelisted models."""
        expected = {
            "life.Task",
            "life.Project",
            "purpose.LifeGoal",
            "purpose.HabitGoal",
            "journal.JournalEntry",
        }
        self.assertEqual(set(NOTE_INDEX_REGISTRY.keys()), expected)

    def test_registry_entries_have_display_fields(self):
        """Each registry entry has a non-empty display_fields list."""
        for model_path, config in NOTE_INDEX_REGISTRY.items():
            self.assertIn("display_fields", config, f"{model_path} missing display_fields")
            self.assertIsInstance(config["display_fields"], list)
            self.assertGreater(len(config["display_fields"]), 0, f"{model_path} has empty display_fields")


class RegistryRenameSignalTest(TestCase):
    """Tests that registry-driven signals fire correctly on entity rename."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="registry_signal@example.com", password="testpass123"
        )

    def test_project_rename_fires_via_registry(self):
        """Renaming a Project via save() triggers registry-driven signal refresh."""
        from apps.life.models import Project

        project = Project.objects.create(
            user=self.user, title="Registry Alpha", description="P"
        )
        note = Note.objects.create(user=self.user, body="Registry signal test")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)

        note.refresh_from_db()
        self.assertIn("Registry Alpha", note.attachments_text)

        # Rename via model save (triggers registry signals)
        project.title = "Registry Beta"
        project.save()

        note.refresh_from_db()
        self.assertIn("Registry Beta", note.attachments_text)
        self.assertNotIn("Registry Alpha", note.attachments_text)

    def test_task_rename_fires_via_registry(self):
        """Renaming a Task via save() triggers registry-driven signal refresh."""
        from apps.life.models import Task

        task = Task.objects.create(
            user=self.user, title="Task Registry Original"
        )
        note = Note.objects.create(user=self.user, body="Task registry test")
        ct = ContentType.objects.get_for_model(task)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=task.pk)

        note.refresh_from_db()
        self.assertIn("Task Registry Original", note.attachments_text)

        task.title = "Task Registry Updated"
        task.save()

        note.refresh_from_db()
        self.assertIn("Task Registry Updated", note.attachments_text)

    def test_no_rename_no_refresh(self):
        """Saving entity without changing display field does NOT trigger refresh."""
        from apps.life.models import Project

        project = Project.objects.create(
            user=self.user, title="Stable Registry", description="P"
        )
        note = Note.objects.create(user=self.user, body="No rename registry test")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)

        note.refresh_from_db()
        original_text = note.attachments_text

        # Save without changing title
        project.description = "Updated desc"
        project.save()

        note.refresh_from_db()
        self.assertEqual(note.attachments_text, original_text)

    def test_new_entity_does_not_trigger(self):
        """Creating a new entity does not trigger rename signals."""
        from apps.life.models import Project

        # Should not raise or error
        Project.objects.create(
            user=self.user, title="Brand New Registry", description="P"
        )


class IntegrityDetectionTest(TestCase):
    """Tests for find_notes_missing_* detection functions."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="integrity_detect@example.com", password="testpass123"
        )

    def _create_project(self, title="Integrity Project"):
        from apps.life.models import Project

        return Project.objects.create(
            user=self.user, title=title, description="P"
        )

    def test_detect_missing_attachments_text(self):
        """Notes with attachments but empty attachments_text are detected."""
        project = self._create_project()
        note = Note.objects.create(user=self.user, body="Has attachment")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)

        # Signal auto-populated attachments_text. Clear it via queryset update.
        Note.objects.filter(pk=note.pk).update(attachments_text="")

        missing = find_notes_missing_attachments_text()
        self.assertEqual(missing.count(), 1)
        self.assertEqual(missing.first().pk, note.pk)

    def test_no_false_positives_attachments_text(self):
        """Notes with populated attachments_text are NOT flagged."""
        project = self._create_project()
        note = Note.objects.create(user=self.user, body="Has attachment OK")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)

        # attachments_text was populated by signal
        note.refresh_from_db()
        self.assertTrue(len(note.attachments_text) > 0)

        missing = find_notes_missing_attachments_text()
        self.assertEqual(missing.count(), 0)

    def test_standalone_notes_not_flagged(self):
        """Notes without attachments are NOT flagged for missing attachments_text."""
        Note.objects.create(user=self.user, body="Standalone note")

        missing = find_notes_missing_attachments_text()
        self.assertEqual(missing.count(), 0)

    def test_detect_missing_search_vector(self):
        """Notes with null search_vector are detected."""
        note = Note.objects.create(user=self.user, body="Has search vector")

        # Clear search_vector via queryset update
        Note.objects.filter(pk=note.pk).update(search_vector=None)

        missing = find_notes_missing_search_vector()
        self.assertEqual(missing.count(), 1)
        self.assertEqual(missing.first().pk, note.pk)

    def test_no_false_positives_search_vector(self):
        """Notes with populated search_vector are NOT flagged."""
        Note.objects.create(user=self.user, body="Good search vector")

        missing = find_notes_missing_search_vector()
        self.assertEqual(missing.count(), 0)


class IntegrityReportTest(TestCase):
    """Tests for get_note_index_integrity_report."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="integrity_report@example.com", password="testpass123"
        )

    def test_clean_report(self):
        """Report with no issues returns zero counts for missing fields."""
        from apps.life.models import Project

        project = Project.objects.create(
            user=self.user, title="Clean Project", description="P"
        )
        note = Note.objects.create(user=self.user, body="Clean note")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)

        report = get_note_index_integrity_report()
        self.assertEqual(report["total_notes"], 1)
        self.assertEqual(report["notes_with_attachments"], 1)
        self.assertEqual(report["missing_attachments_text"], 0)
        self.assertEqual(report["missing_search_vector"], 0)

    def test_report_detects_issues(self):
        """Report counts missing fields correctly."""
        from apps.life.models import Project

        project = Project.objects.create(
            user=self.user, title="Issue Project", description="P"
        )
        note = Note.objects.create(user=self.user, body="Issue note")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)

        # Simulate stale state
        Note.objects.filter(pk=note.pk).update(attachments_text="", search_vector=None)

        report = get_note_index_integrity_report()
        self.assertEqual(report["missing_attachments_text"], 1)
        self.assertEqual(report["missing_search_vector"], 1)


class IntegrityRepairTest(TestCase):
    """Tests for repair_notes_missing_index."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="integrity_repair@example.com", password="testpass123"
        )

    def test_repair_fixes_missing_attachments_text(self):
        """repair_notes_missing_index rebuilds missing attachments_text."""
        from apps.life.models import Project

        project = Project.objects.create(
            user=self.user, title="Repair Att Project", description="P"
        )
        note = Note.objects.create(user=self.user, body="Repair att note")
        ct = ContentType.objects.get_for_model(project)
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)

        # Clear attachments_text
        Note.objects.filter(pk=note.pk).update(attachments_text="")

        result = repair_notes_missing_index()
        self.assertGreaterEqual(result["notes_repaired"], 1)

        note.refresh_from_db()
        self.assertIn("Repair Att Project", note.attachments_text)

    def test_repair_fixes_missing_search_vector(self):
        """repair_notes_missing_index rebuilds missing search_vector."""
        note = Note.objects.create(user=self.user, body="Repair sv note")

        # Clear search_vector
        Note.objects.filter(pk=note.pk).update(search_vector=None)

        result = repair_notes_missing_index()
        self.assertGreaterEqual(result["notes_repaired"], 1)

        note.refresh_from_db()
        self.assertIsNotNone(note.search_vector)

    def test_repair_idempotent(self):
        """Running repair on clean data returns zero repairs."""
        Note.objects.create(user=self.user, body="Already clean")

        result = repair_notes_missing_index()
        self.assertEqual(result["notes_repaired"], 0)


class IntegrityCommandTest(TestCase):
    """Tests for the note_index_integrity_report management command."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="integrity_cmd@example.com", password="testpass123"
        )

    def test_command_shows_report(self):
        """Command outputs the integrity report."""
        Note.objects.create(user=self.user, body="Command report test")

        out = StringIO()
        call_command("note_index_integrity_report", stdout=out)
        output = out.getvalue()

        self.assertIn("Total notes:", output)
        self.assertIn("Missing attachments_text:", output)
        self.assertIn("Missing search_vector:", output)

    def test_command_clean_report(self):
        """Command shows success message when no issues found."""
        Note.objects.create(user=self.user, body="All clean")

        out = StringIO()
        call_command("note_index_integrity_report", stdout=out)
        self.assertIn("No integrity issues found", out.getvalue())

    def test_command_dry_run(self):
        """Command --dry-run shows issues without repairing."""
        note = Note.objects.create(user=self.user, body="Dry run cmd test")
        Note.objects.filter(pk=note.pk).update(search_vector=None)

        out = StringIO()
        call_command("note_index_integrity_report", dry_run=True, stdout=out)
        output = out.getvalue()
        self.assertIn("DRY RUN", output)

        # Verify not actually repaired
        note.refresh_from_db()
        self.assertIsNone(note.search_vector)

    def test_command_repair(self):
        """Command --repair fixes detected issues."""
        note = Note.objects.create(user=self.user, body="Repair cmd test")
        Note.objects.filter(pk=note.pk).update(search_vector=None)

        out = StringIO()
        call_command("note_index_integrity_report", repair=True, stdout=out)
        output = out.getvalue()
        self.assertIn("Repair complete", output)

        # Verify repaired
        note.refresh_from_db()
        self.assertIsNotNone(note.search_vector)

    def test_command_issues_without_repair_flag(self):
        """Command without --repair shows warning about issues."""
        note = Note.objects.create(user=self.user, body="No repair flag test")
        Note.objects.filter(pk=note.pk).update(search_vector=None)

        out = StringIO()
        call_command("note_index_integrity_report", stdout=out)
        self.assertIn("Run with --repair to fix", out.getvalue())
