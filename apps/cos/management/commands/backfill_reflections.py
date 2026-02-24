"""
Management command to backfill CosReflection from existing EventReflection data.

Migrates completed EventReflection records into CosReflection, preserving
the user, source, date, and answer text. Sentiment is auto-detected.

Usage:
    python manage.py backfill_reflections                  # All completed
    python manage.py backfill_reflections --days 30        # Last 30 days
    python manage.py backfill_reflections --dry-run        # Preview only
    python manage.py backfill_reflections --user-id 42     # Single user
"""

import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = "Backfill CosReflection from existing EventReflection data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=0,
            help="Only backfill the last N days (0 = all time).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be backfilled without creating records.",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            default=None,
            help="Only backfill for a specific user ID.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Process records in batches of this size.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        days = options["days"]
        user_id = options["user_id"]
        batch_size = options["batch_size"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no records will be created."))

        # Import EventReflection
        try:
            from apps.core.blueprint.models import EventReflection
        except ImportError:
            self.stderr.write(self.style.ERROR("EventReflection model not found."))
            return

        from apps.cos.models import CosReflection
        from apps.cos.services.reflection_service import CosReflectionService

        # Build queryset
        qs = EventReflection.objects.filter(status=EventReflection.STATUS_COMPLETED)

        if days:
            cutoff = timezone.now() - timedelta(days=days)
            qs = qs.filter(completed_at__gte=cutoff)

        if user_id:
            qs = qs.filter(user_id=user_id)

        total = qs.count()
        self.stdout.write(f"Found {total} completed EventReflection records to process.")

        created = 0
        skipped = 0
        errors = 0

        # Resolve content types for source mapping
        source_type_to_model = self._get_source_type_map()

        for reflection in qs.iterator(chunk_size=batch_size):
            try:
                # Check if already backfilled (dedup by user + date + source_title)
                existing = CosReflection.objects.filter(
                    user=reflection.user,
                    activity_date=reflection.event_date,
                    text__startswith=reflection.source_title[:50],
                ).exists()

                if existing:
                    skipped += 1
                    continue

                # Extract text from answers JSON
                text = self._extract_answer_text(reflection)
                if not text:
                    skipped += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f"  Would create: user={reflection.user_id} "
                        f"date={reflection.event_date} "
                        f"source='{reflection.source_title}'"
                    )
                    created += 1
                    continue

                # Determine content type and object_id from source
                ct, obj_id = self._resolve_source(
                    reflection, source_type_to_model,
                )

                if not ct:
                    skipped += 1
                    continue

                # Detect activity type from source title
                from apps.cos.services.prompt_templates import detect_activity_type

                activity_type = detect_activity_type(reflection.source_title)

                # Detect sentiment
                sentiment = CosReflectionService.detect_sentiment(text)

                CosReflection.objects.create(
                    user=reflection.user,
                    content_type=ct,
                    object_id=obj_id,
                    text=text,
                    sentiment=sentiment,
                    activity_date=reflection.event_date,
                    activity_type=activity_type,
                    prompt_text="[Backfilled from EventReflection]",
                )
                created += 1

            except Exception as e:
                errors += 1
                logger.error(
                    "Backfill error for EventReflection %s: %s",
                    reflection.pk, e,
                )
                if errors > 50:
                    self.stderr.write(
                        self.style.ERROR("Too many errors (>50), aborting.")
                    )
                    break

        # Summary
        action = "Would create" if dry_run else "Created"
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Backfill complete: {action} {created}, "
            f"Skipped {skipped}, Errors {errors} "
            f"(of {total} total)"
        ))

    def _extract_answer_text(self, reflection):
        """Extract meaningful text from EventReflection answers JSON."""
        answers = reflection.answers or {}
        if not answers:
            return ""

        # Answers are keyed by question index: {"0": "answer text", ...}
        parts = []
        for key in sorted(answers.keys()):
            answer = answers[key]
            if isinstance(answer, str) and answer.strip():
                parts.append(answer.strip())
            elif isinstance(answer, dict) and answer.get("text"):
                parts.append(answer["text"].strip())

        return " ".join(parts) if parts else ""

    def _resolve_source(self, reflection, source_type_to_model):
        """Resolve EventReflection source_type/source_id to ContentType + object_id."""
        model_class = source_type_to_model.get(reflection.source_type)
        if not model_class:
            return None, None

        ct = ContentType.objects.get_for_model(model_class)

        # Try to parse source_id as int
        try:
            obj_id = int(reflection.source_id)
        except (ValueError, TypeError):
            return None, None

        return ct, obj_id

    def _get_source_type_map(self):
        """Map EventReflection source_type strings to model classes."""
        mapping = {}
        try:
            from apps.calendar_engine.models import CalendarEvent
            mapping["calendar"] = CalendarEvent
        except ImportError:
            pass

        try:
            from apps.health.models import WorkoutLog
            mapping["workout"] = WorkoutLog
        except ImportError:
            pass

        return mapping
