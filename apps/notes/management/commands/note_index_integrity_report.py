"""
Management command to report on and repair Notes index integrity.

Detects missing attachments_text and search_vector data, and optionally
repairs them using existing service helpers.

Usage:
    # Show integrity report
    python manage.py note_index_integrity_report

    # Show report and repair issues
    python manage.py note_index_integrity_report --repair

    # Dry run (show what would be repaired)
    python manage.py note_index_integrity_report --dry-run

    # Custom batch size for repair
    python manage.py note_index_integrity_report --repair --batch-size 1000
"""

from django.core.management.base import BaseCommand

from apps.notes.services import get_note_index_integrity_report, repair_notes_missing_index


class Command(BaseCommand):
    help = "Report on Notes index integrity and optionally repair issues."

    def add_arguments(self, parser):
        parser.add_argument(
            "--repair",
            action="store_true",
            default=False,
            help="Repair any detected integrity issues.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Show what would be repaired without making changes.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Number of notes to process per batch during repair (default 500).",
        )

    def handle(self, *args, **options):
        repair = options["repair"]
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]

        report = get_note_index_integrity_report()

        self.stdout.write(f"Total notes: {report['total_notes']}")
        self.stdout.write(f"Notes with attachments: {report['notes_with_attachments']}")
        self.stdout.write(f"Missing attachments_text: {report['missing_attachments_text']}")
        self.stdout.write(f"Missing search_vector: {report['missing_search_vector']}")

        issues = report["missing_attachments_text"] + report["missing_search_vector"]

        if issues == 0:
            self.stdout.write(self.style.SUCCESS("No integrity issues found."))
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"DRY RUN — {issues} note(s) would be repaired.")
            )
            return

        if repair:
            result = repair_notes_missing_index(batch_size=batch_size)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Repair complete. Fixed {result['notes_repaired']} note(s)."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"{issues} issue(s) found. Run with --repair to fix."
                )
            )
