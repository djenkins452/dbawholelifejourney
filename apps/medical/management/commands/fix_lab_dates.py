"""
One-time fix: re-parse extracted text from medical documents and update
collected_at dates on lab results that have today's date (the fallback).

This fixes results where the date parser failed during import and
timezone.now() was used as fallback.
"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.medical.models import LabResult, MedicalDocument
from apps.medical.services.lab_parser import parse_lab_text

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fix lab result dates by re-parsing extracted text from documents"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would change without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Find all medical documents with extracted text
        docs = MedicalDocument.objects.exclude(
            extracted_text__isnull=True
        ).exclude(extracted_text="")

        total_fixed = 0

        for doc in docs:
            self.stdout.write(f"\nDoc: {doc.original_filename} (user: {doc.user.email})")

            # Re-parse the text
            parsed_results = parse_lab_text(doc.extracted_text)
            if not parsed_results:
                self.stdout.write("  No parsed results from text")
                continue

            # Build a lookup: test_name -> collected_at from parser
            parsed_dates = {}
            for pr in parsed_results:
                if pr.collected_at:
                    key = pr.test_name.strip().lower()
                    parsed_dates[key] = pr.collected_at

            if not parsed_dates:
                self.stdout.write("  Parser found no dates in extracted text")

                # Show what the parser sees
                for pr in parsed_results[:5]:
                    self.stdout.write(
                        f"    {pr.test_name}: collected_at={pr.collected_at}"
                    )
                continue

            # Get a representative parsed date (most common)
            from collections import Counter
            date_counts = Counter(parsed_dates.values())
            most_common_date = date_counts.most_common(1)[0][0]
            self.stdout.write(f"  Parsed date from text: {most_common_date}")

            # Find lab results linked to this document
            results = LabResult.objects.filter(
                medical_document=doc, user=doc.user
            )

            for result in results:
                # Check if this result's date looks like a fallback (same day as import)
                # Compare to document created_at — if collected_at is within 1 day of
                # when the document was uploaded, it's likely a timezone.now() fallback
                time_diff = abs(
                    (result.collected_at - doc.created_at).total_seconds()
                )
                is_likely_fallback = time_diff < 86400  # Within 24 hours

                if not is_likely_fallback:
                    continue  # Date looks correct, skip

                # Try to find the correct date from parsed results
                raw_key = result.raw_test_name.strip().lower()
                correct_date = parsed_dates.get(raw_key, most_common_date)

                if correct_date and correct_date != result.collected_at:
                    # Make it timezone-aware if needed
                    if timezone.is_naive(correct_date):
                        correct_date = timezone.make_aware(correct_date)

                    self.stdout.write(
                        f"  FIX: {result.raw_test_name}: "
                        f"{result.collected_at} -> {correct_date}"
                    )

                    if not dry_run:
                        result.collected_at = correct_date
                        result.save(update_fields=['collected_at', 'updated_at'])
                        total_fixed += 1

        if dry_run:
            self.stdout.write(f"\nDRY RUN: Would fix {total_fixed} results")
        else:
            self.stdout.write(f"\nFixed {total_fixed} result dates")
