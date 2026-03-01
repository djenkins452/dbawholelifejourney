"""
Management command to refresh attachment display strings and search vectors
for notes with attachments.

Fixes stale attachments_text when attached entities have been renamed.

Usage:
    # Refresh all notes with attachments
    python manage.py refresh_note_attachments_index

    # Refresh notes attached to a specific content type
    python manage.py refresh_note_attachments_index --content-type "life.project"

    # Refresh notes attached to a specific entity
    python manage.py refresh_note_attachments_index --content-type "life.project" --object-id 42

    # Dry run (no writes)
    python manage.py refresh_note_attachments_index --dry-run

    # Custom batch size
    python manage.py refresh_note_attachments_index --batch-size 1000
"""

import time

from django.core.management.base import BaseCommand

from apps.notes.services import (
    refresh_notes_for_content_type,
    refresh_notes_for_entity,
    refresh_notes_with_attachments,
)


class Command(BaseCommand):
    help = "Refresh attachment display strings and search vectors for notes with attachments."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            default=False,
            help="Refresh all notes that have attachments (default if no scope specified).",
        )
        parser.add_argument(
            "--content-type",
            type=str,
            default=None,
            help='Content type in "app.model" format (e.g. "life.project").',
        )
        parser.add_argument(
            "--object-id",
            type=int,
            default=None,
            help="Object ID of a specific entity (requires --content-type).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Number of notes to process per batch (default 500).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print counts only; do not write changes.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            default=False,
            help="Extra logging output.",
        )

    def handle(self, *args, **options):
        content_type = options["content_type"]
        object_id = options["object_id"]
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]
        verbose = options["verbose"]

        if object_id and not content_type:
            self.stderr.write(
                self.style.ERROR("--object-id requires --content-type.")
            )
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be written."))

        start_time = time.time()

        if content_type and object_id:
            # Specific entity
            scope = f"{content_type}:{object_id}"
            if verbose:
                self.stdout.write(f"Scope: entity {scope}")
            result = refresh_notes_for_entity(
                content_type_str=content_type,
                object_id=object_id,
                batch_size=batch_size,
                dry_run=dry_run,
            )
        elif content_type:
            # All entities of a content type
            scope = content_type
            if verbose:
                self.stdout.write(f"Scope: all {scope} entities")
            result = refresh_notes_for_content_type(
                content_type_str=content_type,
                batch_size=batch_size,
                dry_run=dry_run,
            )
        else:
            # All notes with attachments
            scope = "all attached notes"
            if verbose:
                self.stdout.write(f"Scope: {scope}")
            result = refresh_notes_with_attachments(
                batch_size=batch_size,
                dry_run=dry_run,
            )

        elapsed = time.time() - start_time

        self.stdout.write(
            f"Scope: {scope}\n"
            f"Notes considered: {result['notes_considered']}\n"
            f"Notes updated: {result['notes_updated']}\n"
            f"Elapsed: {elapsed:.2f}s"
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN complete — nothing written."))
        else:
            self.stdout.write(self.style.SUCCESS("Refresh complete."))
