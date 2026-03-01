"""
Management command to backfill semantic embeddings for existing Notes.

Generates embeddings for Notes that don't have one yet (or all Notes),
using the OpenAI text-embedding-3-small model via the embeddings service.

Usage:
    # Backfill all notes (including those with existing embeddings)
    python manage.py backfill_note_embeddings

    # Only notes missing embeddings
    python manage.py backfill_note_embeddings --missing-only

    # Limit number of notes to process
    python manage.py backfill_note_embeddings --missing-only --limit 100

    # Custom batch size
    python manage.py backfill_note_embeddings --batch-size 25
"""

import time

from django.core.management.base import BaseCommand

from apps.notes.embeddings import update_note_embedding
from apps.notes.models import Note


class Command(BaseCommand):
    help = "Backfill semantic embeddings for Notes using OpenAI."

    def add_arguments(self, parser):
        parser.add_argument(
            "--missing-only",
            action="store_true",
            default=False,
            help="Only process notes that have no embedding yet.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max number of notes to process (0 = unlimited).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Number of notes to process per batch (default 50).",
        )

    def handle(self, *args, **options):
        missing_only = options["missing_only"]
        limit = options["limit"]
        batch_size = options["batch_size"]

        # Build queryset
        queryset = Note.all_objects.all().order_by("pk")
        if missing_only:
            queryset = queryset.filter(embedding__isnull=True)

        total_available = queryset.count()
        if limit > 0:
            total_to_process = min(limit, total_available)
        else:
            total_to_process = total_available

        self.stdout.write(
            f"Notes to process: {total_to_process} "
            f"(available: {total_available}, missing-only: {missing_only})"
        )

        if total_to_process == 0:
            self.stdout.write(self.style.SUCCESS("No notes to process."))
            return

        processed = 0
        succeeded = 0
        failed = 0
        start_time = time.time()

        # Process in batches
        offset = 0
        while processed < total_to_process:
            batch = list(queryset[offset : offset + batch_size])
            if not batch:
                break

            for note in batch:
                if processed >= total_to_process:
                    break

                result = update_note_embedding(note)
                if result:
                    succeeded += 1
                else:
                    failed += 1
                processed += 1

                if processed % 10 == 0:
                    self.stdout.write(
                        f"  Progress: {processed}/{total_to_process} "
                        f"(success: {succeeded}, failed: {failed})"
                    )

            offset += batch_size

        elapsed = time.time() - start_time
        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete. "
                f"Processed: {processed}, "
                f"Succeeded: {succeeded}, "
                f"Failed: {failed}, "
                f"Elapsed: {elapsed:.1f}s"
            )
        )
